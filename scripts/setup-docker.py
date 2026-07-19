#!/usr/bin/env python
"""Docker 环境一键检查与镜像准备脚本。

本脚本用于在运行 Litmus Agent 前检查 Docker daemon 是否可达，并确保
默认沙箱镜像 ``python:3.11-slim`` 已提前拉取到本地。

使用方式：
    python scripts/setup-docker.py

退出码：
    0 — Docker 就绪且镜像已存在/拉取成功。
    1 — Docker daemon 未启动或镜像拉取失败。
"""

from __future__ import annotations

import argparse
import sys

import docker
from docker import DockerClient

DEFAULT_IMAGE = "python:3.11-slim"


def check_docker_available(client: DockerClient | None = None) -> bool:
    """检查 Docker daemon 是否可达。

    参数：
        client: 可选的 DockerClient 实例；未传入时通过 ``docker.from_env()`` 创建。

    返回：
        daemon 可达返回 True，否则返回 False。
    """
    try:
        docker_client = client or docker.from_env()
        return bool(docker_client.ping())
    except Exception:
        return False


def ensure_image(
    image: str,
    client: DockerClient | None = None,
) -> tuple[bool, str]:
    """确保指定镜像已存在；不存在则尝试拉取。

    参数：
        image: 镜像名称，例如 ``python:3.11-slim``。
        client: 可选的 DockerClient 实例；未传入时通过 ``docker.from_env()`` 创建。

    返回：
        (是否成功, 状态信息)
    """
    try:
        docker_client = client or docker.from_env()
        existing = docker_client.images.list(name=image)
        if existing:
            return True, f"镜像 {image} 已存在，无需拉取。"

        print(f"正在拉取镜像 {image}，请稍候...")
        docker_client.images.pull(image)
        return True, f"镜像 {image} 拉取完成。"
    except Exception as exc:  # noqa: BLE001
        return False, f"镜像 {image} 拉取失败：{exc}"


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="检查 Docker 环境并准备 Litmus Agent 默认沙箱镜像。",
    )
    parser.add_argument(
        "--image",
        default=DEFAULT_IMAGE,
        help=f"指定沙箱镜像名称（默认：{DEFAULT_IMAGE}）",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI 入口：检查 Docker 并准备默认镜像。

    参数：
        argv: 命令行参数列表；None 时使用 sys.argv。

    返回：
        退出码：0 就绪，1 未就绪。
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    if not check_docker_available():
        print("错误：Docker daemon 未启动或无法连接。", file=sys.stderr)
        print("排查建议：", file=sys.stderr)
        print("  1. 确保 Docker Desktop 或 Docker Engine 已运行。", file=sys.stderr)
        print("  2. 检查当前用户是否有权限访问 Docker daemon。", file=sys.stderr)
        return 1

    print("Docker daemon 已连接。")
    success, message = ensure_image(args.image)
    print(message)
    if not success:
        print("排查建议：", file=sys.stderr)
        print("  1. 检查网络是否能访问 Docker Hub（registry-1.docker.io）。", file=sys.stderr)
        print("  2. 在 Docker Desktop 中配置镜像加速器或 HTTPS proxy。", file=sys.stderr)
        print("  3. 尝试手动执行：docker pull <image_name>", file=sys.stderr)
        print("  4. 内网环境可手动导入离线镜像：docker load -i image.tar", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
