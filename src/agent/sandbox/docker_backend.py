"""Docker 沙箱后端 —— 负责与 Docker Engine 通信。

本模块当前职责：
  1. ping()：检查 Docker daemon 是否可达
  2. ensure_image()：确保执行用的镜像已经在本地
  3. create_container()：创建并启动一个长期运行的容器
  4. remove_container()：停止并删除当前容器
  5. execute_code()：在容器内执行 Python 代码并捕获结果
  6. put_file()：把文件注入容器
  7. get_file()：从容器提取文件

seccomp 等更细粒度安全策略可在未来通过 security_opt 参数扩展。
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import posixpath
import tarfile
import uuid
from typing import Any, cast

import docker
from docker import DockerClient
from docker.models.containers import Container

from agent.sandbox.base import ExecutionResult

logger = logging.getLogger(__name__)

__all__ = ["DockerSandboxBackend", "ExecutionResult"]


def _host_bind_user() -> str | None:
    """bind 模式容器运行用户（TD-015 单元 C 双模用户模型）。

    POSIX：返回宿主 ``uid:gid``，保证容器写出的文件属主与宿主用户一致；
    其他平台（Windows Docker Desktop 经文件共享层自动映射属主）：
    返回 None，调用方维持默认 nobody。
    """
    getuid = getattr(os, "getuid", None)
    getgid = getattr(os, "getgid", None)
    if os.name == "posix" and getuid is not None and getgid is not None:
        return f"{getuid()}:{getgid()}"
    return None


class DockerSandboxBackend:
    """Docker 沙箱后端。

    使用 docker-py 与 Docker Engine 通信。所有公开方法都是 async，
    以便未来无缝接入 async 的 Agent 主循环；内部同步的 docker-py 调用
    通过 asyncio.to_thread() 放到线程池执行，避免阻塞事件循环。

    属性：
        image: 用于执行代码的 Docker 镜像名。
        container_id: 当前管理的容器 ID，没有则为 None。

    注意：
        构造时会尝试连接 Docker daemon。如果连接失败（例如 Docker Desktop
        未启动），`_client` 会被置为 None，后续 `ping()` 将返回 False。
    """

    def __init__(
        self,
        image: str = "python:3.11-slim",
        timeout: int = 30,
        workspace_volume: str | None = None,
        cleanup_workspace: bool = True,
        image_registry: str | None = None,
        workspace_bind: str | None = None,
        network_mode: str = "none",
        allow_setup_network: bool = False,
        mem_limit: str | None = None,
    ) -> None:
        """初始化 Docker 后端。

        参数：
            image: 执行代码时使用的 Docker 镜像，默认 python:3.11-slim。
            timeout: 代码执行默认超时时间（秒），默认 30 秒。
            workspace_volume: 用于跨调用持久化文件的 Docker 卷名称；
                为 None 时自动生成唯一名称，避免多 session 冲突。
            cleanup_workspace: 后端关闭时是否删除 workspace 卷，默认 True。
            image_registry: 镜像源地址（TD-007，如 docker.m.daocloud.io）；
                None 表示从 Docker Hub 拉取。
            workspace_bind: TD-015 单元 C——宿主机目录 bind 挂载到 /workspace
                （替代命名卷）。POSIX 下容器以宿主 uid:gid 运行并跳过
                chown 65534；Windows 维持 nobody（Docker Desktop 文件共享
                层自动映射属主）。宿主机目录不属于后端资产，close 不清理。
            network_mode: TD-010——容器池的网络模式，原样透传给 Docker
                （none/bridge/...），默认 "none" 禁网。
            allow_setup_network: TD-010——安装阶段自动放行开关。存为实例
                属性 `setup_network_enabled` 供工具层查询；为 True 时
                `execute_code(allow_network=True)` 会现场创建有网（bridge）
                临时容器执行，用完即销毁不入池。
            mem_limit: TD-017——实例级默认内存上限，docker 风格字符串
                （如 "256m"），None 表示不限制；作为 `_do_create_container`
                的默认 memory_limit，调用方显式传参优先。
        """
        self.image: str = image
        self.timeout: int = timeout
        self.image_registry: str | None = image_registry
        self.network_mode: str = network_mode
        self.setup_network_enabled: bool = allow_setup_network
        self.mem_limit: str | None = mem_limit
        self.workspace_volume: str = (
            workspace_volume or f"hermes-workspace-{uuid.uuid4().hex[:8]}"
        )
        self.cleanup_workspace: bool = cleanup_workspace
        self.workspace_bind: str | None = workspace_bind
        try:
            self._client: DockerClient | None = docker.from_env()
        except Exception:
            self._client = None
        self._container: Container | None = None
        self._pool: list[Container] = []

    def _get_client(self) -> DockerClient | None:
        """返回内部 Docker client，连接失败时可能为 None。"""
        return self._client

    async def ping(self) -> bool:
        """检查 Docker daemon 是否可达。

        返回：
            daemon 可达返回 True，否则返回 False。
        """
        client = self._get_client()
        if client is None:
            return False
        try:
            return bool(await asyncio.to_thread(client.ping))
        except Exception:
            return False

    def _resolve_pull_image(self) -> str:
        """解析拉取用的完整镜像名（TD-007）。

        规则：
          - 未配置 registry：返回 `self.image` 原名（Docker Hub）；
          - 官方镜像（无命名空间）：`{registry}/library/{image}`；
          - 含命名空间的镜像：`{registry}/{image}`；
          - registry 自动剥离 `http(s)://` 前缀与尾部 `/`。
        """
        if not self.image_registry:
            return self.image
        registry = self.image_registry.strip()
        for prefix in ("https://", "http://"):
            if registry.startswith(prefix):
                registry = registry[len(prefix):]
        registry = registry.rstrip("/")
        if "/" in self.image:
            return f"{registry}/{self.image}"
        return f"{registry}/library/{self.image}"

    async def ensure_image(self) -> bool:
        """确保执行镜像已存在于本地。

        流程：
          1. 检查本地是否已有该镜像；有则直接返回 True，不触发拉取；
          2. 没有则按 `_resolve_pull_image()` 拉取；
          3. 拉取名与 `self.image` 不同（镜像源场景）时打标回原名，
             保证后续容器创建使用 `self.image` 能找到镜像。

        返回：
            镜像就绪返回 True，检查或拉取失败返回 False。
        """
        client = self._get_client()
        if client is None:
            return False
        try:
            images = await asyncio.to_thread(client.images.list, name=self.image)
            if images:
                return True
            pull_image = self._resolve_pull_image()
            pulled = await asyncio.to_thread(client.images.pull, pull_image)
            if pull_image != self.image:
                await asyncio.to_thread(pulled.tag, self.image)
            return True
        except Exception:
            return False

    async def _do_create_container(
        self,
        command: str = "tail -f /dev/null",
        memory_limit: str | None = None,
        network_mode: str | None = "none",
        user: str | None = "nobody",
        read_only: bool = True,
        tmpfs: dict[str, str] | None = None,
        seccomp_profile: str | None = None,
    ) -> Container | None:
        """实际执行容器创建和启动的私有方法。

        不包含旧容器清理和 self._container 赋值，供 create_container()
        和预热池复用。
        """
        client = self._get_client()
        if client is None:
            return None
        try:
            # TD-015 单元 C：bind 模式以宿主路径替代命名卷挂载 /workspace。
            volumes: dict[str, dict[str, str]] = (
                {self.workspace_bind: {"bind": "/workspace", "mode": "rw"}}
                if self.workspace_bind is not None
                else {self.workspace_volume: {"bind": "/workspace", "mode": "rw"}}
            )
            # bind 模式用户模型双模：POSIX 传宿主 uid:gid（保证写出的文件
            # 属主正确）；Windows Docker Desktop 经文件共享层自动映射属主，
            # 维持 nobody。仅在调用方未显式指定 user 时生效。
            effective_user = user
            if self.workspace_bind is not None and user == "nobody":
                effective_user = _host_bind_user() or user
            create_kwargs: dict[str, Any] = {
                "image": self.image,
                "command": command,
                "detach": True,
                "stdin_open": True,
                "tty": False,
                "network_mode": network_mode,
                "user": effective_user,
                "read_only": read_only,
                "volumes": volumes,
                # TD-018：行业标准加固——drop 全部 capabilities，仅回加 CHOWN
                # （EVAL-010 的 workspace chown 以 root exec 执行，需 CAP_CHOWN；
                # 沙箱载荷以 nobody 运行本就无 cap，且 no-new-privileges 阻断
                # setuid/file-caps 提权，无法获得 CHOWN）。实测：缺 CHOWN 时
                # chown 报 EPERM，workspace 将不可写。
                "cap_drop": ["ALL"],
                "cap_add": ["CHOWN"],
                "security_opt": ["no-new-privileges"],
            }
            if self.workspace_bind is not None:
                # bind 模式：宿主 uid 在容器内无 passwd 条目，HOME 指向只读层
                # 会导致工具写家目录失败；指向可写 tmpfs 的 /tmp。
                create_kwargs["environment"] = {"HOME": "/tmp"}
            # TD-017：实例级 mem_limit 作为默认内存上限，调用方显式传参优先。
            effective_memory_limit = (
                memory_limit if memory_limit is not None else self.mem_limit
            )
            if effective_memory_limit is not None:
                create_kwargs["mem_limit"] = effective_memory_limit
            if tmpfs is not None:
                create_kwargs["tmpfs"] = tmpfs
            elif read_only:
                create_kwargs["tmpfs"] = {"/tmp": "rw,noexec,nosuid,size=64m"}
            if seccomp_profile is not None:
                # 追加到默认 no-new-privileges 之后（合并而非覆盖）。
                create_kwargs.setdefault("security_opt", []).append(
                    f"seccomp={seccomp_profile}"
                )
            container = await asyncio.to_thread(
                client.containers.create,
                **create_kwargs,
            )
            # create 成功后 start 等后续步骤若失败，必须兜底删除已创建的容器，
            # 否则返回 None 的调用方无法感知该容器，造成容器泄漏。
            try:
                await asyncio.to_thread(container.start)
                # EVAL-010：workspace volume 默认 root 属主，容器内 nobody 无法写入。
                # 创建后以 root 将 volume 属主改为 nobody（uid/gid 65534，Debian 系
                # 镜像标准 nobody），保证工具写入与沙箱代码写入权限一致。
                # 数字 uid 不依赖用户存在；失败仅警告降级，不阻塞容器创建。
                # TD-015 单元 C：bind 模式跳过 chown——不篡改宿主文件属主。
                if self.workspace_bind is None:
                    try:
                        exit_code, output = await asyncio.to_thread(
                            container.exec_run,
                            "chown -R 65534:65534 /workspace",
                            user="root",
                        )
                        if exit_code != 0:
                            logger.warning(
                                "workspace chown 失败（exit=%s）：%s",
                                exit_code,
                                output,
                            )
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("workspace chown 执行异常：%s", exc)
            except Exception as exc:  # noqa: BLE001
                logger.warning("容器创建后启动失败，兜底清理已创建容器：%s", exc)
                try:
                    await asyncio.to_thread(container.remove, force=True)
                except Exception as rm_exc:  # noqa: BLE001
                    logger.warning("失败容器兜底清理异常（容器可能残留）：%s", rm_exc)
                return None
            return container
        except Exception:
            return None

    async def create_container(
        self,
        command: str = "tail -f /dev/null",
        memory_limit: str | None = None,
        network_mode: str | None = "none",
        user: str | None = "nobody",
        read_only: bool = True,
        tmpfs: dict[str, str] | None = None,
        seccomp_profile: str | None = None,
    ) -> Container | None:
        """创建并启动一个受安全限制的 Docker 容器。

        如果后端已经管理了一个容器，会先移除旧容器再创建新容器，
        避免资源泄漏。旧容器移除失败时不会继续创建新容器。

        默认安全策略：
          - network_mode="none"：禁止外部网络访问
          - user="nobody"：以非 root 用户运行
          - read_only=True：根文件系统只读
          - tmpfs={"/tmp": "rw,noexec,nosuid,size=64m"}：/tmp 可写但隔离
          - cap_drop=["ALL"] + cap_add=["CHOWN"]：drop 全部 capabilities，
            仅保留 workspace chown 所需的 CHOWN（TD-018）
          - security_opt=["no-new-privileges"]：禁止进程提权（TD-018）

        参数：
            command: 容器启动后执行的命令，默认保持容器长期运行。
            memory_limit: 内存限制，例如 "256m"、"512m"。
            network_mode: 网络模式，默认 "none" 表示无网络。
            user: 容器内运行用户，默认 "nobody"。
            read_only: 是否以只读模式挂载根文件系统，默认 True。
            tmpfs: tmpfs 挂载配置，默认提供 /tmp 可写目录。
            seccomp_profile: seccomp 配置文件路径，None 表示使用 Docker 默认策略。

        返回：
            创建成功返回 Container 对象，失败返回 None。
        """
        if not await self.remove_container():
            return None
        container = await self._do_create_container(
            command=command,
            memory_limit=memory_limit,
            network_mode=network_mode,
            user=user,
            read_only=read_only,
            tmpfs=tmpfs,
            seccomp_profile=seccomp_profile,
        )
        if container is not None:
            self._container = container
        return container

    async def warmup(self, count: int = 2) -> bool:
        """预热容器池。

        提前创建 count 个容器放入池中，供后续 execute_code / put_file
        优先使用，减少执行时的容器创建延迟。

        参数：
            count: 预热的容器数量，默认 2。

        返回：
            全部创建成功返回 True，任一失败返回 False。
            部分失败时，已经成功创建的容器会保留在池中。
        """
        for _ in range(count):
            container = await self._do_create_container(network_mode=self.network_mode)
            if container is None:
                return False
            self._pool.append(container)
        return True

    async def _acquire_container(self) -> Container | None:
        """从池中获取一个容器，池空则新建。

        返回：
            可用容器，失败返回 None。
        """
        if self._pool:
            return self._pool.pop()
        return await self._do_create_container(network_mode=self.network_mode)

    async def _release_and_replenish(self, container: Container) -> None:
        """释放使用过的容器，并尝试补充一个新容器到池中。

        当前采用简单策略：使用过的容器直接销毁，避免污染；然后异步
        创建一个新容器补充到池中，保持池大小稳定。

        参数：
            container: 需要释放的容器。
        """
        try:
            await asyncio.to_thread(container.stop)
            await asyncio.to_thread(container.remove)
        except Exception:
            pass

        replacement = await self._do_create_container(network_mode=self.network_mode)
        if replacement is not None:
            self._pool.append(replacement)

    async def remove_container(self) -> bool:
        """停止并删除当前管理的容器。

        返回：
            成功或当前无容器返回 True，停止/删除失败返回 False。
        """
        if self._container is None:
            return True
        container = self._container
        self._container = None
        try:
            await asyncio.to_thread(container.stop)
            await asyncio.to_thread(container.remove)
            return True
        except Exception:
            return False

    async def _destroy_ephemeral_container(self, container: Container) -> None:
        """销毁有网临时容器（TD-010）——不入池、不补充，异常仅告警降级。

        参数：
            container: 需要销毁的临时容器。
        """
        try:
            await asyncio.to_thread(container.stop)
            await asyncio.to_thread(container.remove)
        except Exception as exc:  # noqa: BLE001
            logger.warning("有网临时容器销毁失败（容器可能残留）：%s", exc)

    async def execute_code(
        self,
        code: str,
        timeout: int | None = None,
        *,
        allow_network: bool = False,
    ) -> ExecutionResult:
        """在容器内执行 Python 代码并返回结果。

        如果当前没有正在运行的容器，会自动创建一个。

        参数：
            code: 要执行的 Python 源代码。
            timeout: 执行超时时间（秒），None 表示使用 backend 默认值。
            allow_network: TD-010——True 时现场创建一个有网（bridge）临时
                容器执行（同一 workspace 卷/bind 挂载，其余加固不变），
                用完立即销毁、不入池；False 维持现状（走禁网容器池）。

        返回：
            ExecutionResult，包含退出码、stdout、stderr 和成功标志。
        """
        client = self._get_client()
        if client is None:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr="Docker client unavailable",
                success=False,
            )

        container: Container | None = None
        try:
            if allow_network:
                # 有网临时容器：固定 bridge（最小暴露面），不入池。
                container = await self._do_create_container(network_mode="bridge")
            else:
                container = await self._acquire_container()
            if container is None:
                return ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr="Failed to create container",
                    success=False,
                )

            encoded = base64.b64encode(code.encode("utf-8")).decode("ascii")
            command = (
                f"python -c \"import base64; "
                f"exec(base64.b64decode('{encoded}'))\""
            )

            exec_kwargs: dict[str, Any] = {"demux": True}
            effective_timeout = timeout if timeout is not None else self.timeout

            # docker-py 的 exec_run 不支持 timeout 参数（7.x 会抛 TypeError），
            # 超时改由 asyncio.wait_for 在外层强制生效。
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(container.exec_run, command, **exec_kwargs),
                    timeout=effective_timeout,
                )
            except (TimeoutError, asyncio.TimeoutError):
                return ExecutionResult(
                    exit_code=-1,
                    stdout="",
                    stderr=f"执行超时（>{effective_timeout}s），已终止等待。",
                    success=False,
                )
            exit_code, output = result
            stdout_bytes, stderr_bytes = (
                output if isinstance(output, tuple) else (output, b"")
            )

            stdout = (
                stdout_bytes.decode("utf-8", errors="replace")
                if stdout_bytes else ""
            )
            stderr = (
                stderr_bytes.decode("utf-8", errors="replace")
                if stderr_bytes else ""
            )

            return ExecutionResult(
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                success=exit_code == 0,
            )
        except Exception as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout="",
                stderr=str(exc),
                success=False,
            )
        finally:
            if container is not None:
                if allow_network:
                    # 有网临时容器用完即销毁，不回池也不补充（池语义不变）。
                    await self._destroy_ephemeral_container(container)
                else:
                    await self._release_and_replenish(container)

    async def put_file(self, container_path: str, content: bytes) -> bool:
        """把文件内容注入容器内指定路径。

        如果当前没有正在运行的容器，会自动创建一个。

        参数：
            container_path: 容器内的目标路径，例如 "/tmp/data.csv"。
            content: 要写入的文件内容。

        返回：
            注入成功返回 True，失败返回 False。
        """
        client = self._get_client()
        if client is None:
            return False

        container: Container | None = None
        try:
            container = await self._acquire_container()
            if container is None:
                return False

            parent_dir = posixpath.dirname(container_path) or "/"
            filename = posixpath.basename(container_path)

            tar_buffer = io.BytesIO()
            with tarfile.open(fileobj=tar_buffer, mode="w") as tar:
                info = tarfile.TarInfo(name=filename)
                info.size = len(content)
                # EVAL-010：与 workspace volume 属主保持一致（nobody），
                # 否则沙箱内代码无法覆盖工具写入的文件。
                info.uid = 65534
                info.gid = 65534
                tar.addfile(info, io.BytesIO(content))
            tar_bytes = tar_buffer.getvalue()

            return bool(
                await asyncio.to_thread(
                    container.put_archive,
                    parent_dir,
                    tar_bytes,
                )
            )
        except Exception:
            return False
        finally:
            if container is not None:
                await self._release_and_replenish(container)

    async def get_file(self, container_path: str) -> bytes | None:
        """从容器内指定路径读取文件内容。

        通过池化容器读取，确保 workspace volume 中的文件对其他调用可见。

        参数：
            container_path: 容器内的文件路径，例如 "/workspace/output.png"。

        返回：
            文件内容 bytes，读取失败或文件不存在返回 None。
        """
        client = self._get_client()
        if client is None:
            return None

        container: Container | None = None
        try:
            container = await self._acquire_container()
            if container is None:
                return None

            data, _stat = await asyncio.to_thread(
                container.get_archive,
                container_path,
            )
            chunks = list(data)
            tar_bytes = b"".join(chunks)

            with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r") as tar:
                member = tar.next()
                if member is None:
                    return None
                file_obj = tar.extractfile(member)
                if file_obj is None:
                    return None
                return file_obj.read()
        except Exception:
            return None
        finally:
            if container is not None:
                await self._release_and_replenish(container)

    @property
    def container_id(self) -> str | None:
        """返回当前管理的容器 ID。"""
        if self._container is None:
            return None
        # docker-py 的 Container.id 类型标注不完整，mypy 会推断为 Any，
        # 这里用 cast 明确返回类型。
        return cast(str, self._container.id)

    def close(self) -> None:
        """关闭 Docker client，释放资源。

        关闭前会移除当前管理的容器、预热池中的所有容器，并根据
        `cleanup_workspace` 决定是否删除 workspace volume，避免泄漏。

        注意：本方法是同步接口，内部直接调用 docker-py 的同步 API。
        如果在 async 事件循环中调用，可能短暂阻塞循环。async 上下文
        应优先使用 `async with` 或显式 `await remove_container()`。
        """
        # remove_container 是 async，但 close 是 sync 接口。
        # 如果调用者已经在 async 上下文里，应该优先 await remove_container()。
        # 这里同步调用 remove 只是为了提供便捷的资源释放入口。
        if self._container is not None:
            container = self._container
            self._container = None
            try:
                container.stop()
                container.remove()
            except Exception:
                pass

        # 清理预热池中的所有容器，防止资源泄漏。
        while self._pool:
            container = self._pool.pop()
            try:
                container.stop()
                container.remove()
            except Exception:
                pass

        # 根据配置删除 workspace volume（bind 模式无卷可删，跳过）。
        if (
            self.cleanup_workspace
            and self.workspace_bind is None
            and self._client is not None
        ):
            try:
                volume = self._client.volumes.get(self.workspace_volume)
                volume.remove()
            except Exception:
                pass

        if self._client is not None:
            self._client.close()
            self._client = None

    async def __aenter__(self) -> DockerSandboxBackend:
        """支持 async with 语法。"""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """退出 async with 时自动关闭 client。"""
        await self.remove_container()
        self.close()
