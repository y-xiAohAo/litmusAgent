"""结构化日志配置 —— 基于 structlog。

为什么不用 Python 标准库 logging？
  1. logging 输出的是字符串，无法按字段搜索
     "User alice completed task" → 想找所有 alice 的日志？只能 grep
  2. logging 的配置（Formatter/Handler/Filter）非常繁琐
  3. structlog 输出的是结构化事件：
     logger.info("task_completed", user="alice", task="analysis", duration=3.2)
     → {"event":"task_completed","user":"alice","task":"analysis","duration":3.2}
     → 可以被 Elasticsearch / Datadog 索引和搜索

两种输出模式：
  json_format=False（开发模式）：
    [info] 2026-04-28 18:00:00 task_completed  user=alice task=analysis
    彩色终端输出，适合开发调试

  json_format=True（生产模式）：
    {"event":"task_completed","user":"alice","task":"analysis","timestamp":"..."}
    每行一个 JSON，可以被日志收集器直接解析

关键概念：Processor 管道
  structlog 的日志处理是通过一系列 processor 组成的管道：
    contextvars.merge_contextvars → add_log_level → TimeStamper → renderer
    每个 processor 修改或增强日志事件，最后 renderer 负责输出
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.typing import Processor


def configure_logging(
    level: str = "INFO",
    json_format: bool = False,
) -> None:
    """配置 structlog 的全局设置。应在应用启动时调用一次。

    参数：
      level:       日志级别（DEBUG/INFO/WARNING/ERROR）
      json_format: True=JSON 行输出，False=彩色终端输出

    配置内容：
      1. 设置 processor 管道（processor 按序处理每条日志）
      2. 设置 wrapper_class（过滤低于指定级别的日志）
      3. 设置 logger_factory（输出目标：stderr）
      4. 同时配置标准库 logging（让使用 logging 的第三方库也输出到 structlog）

    processor 管道（按执行顺序）：
      1. merge_contextvars → 合并上下文变量
      2. add_log_level → 添加 "level" 字段（info/warning/error）
      3. TimeStamper → 添加 "timestamp" 字段（ISO 8601 格式）
      4. format_exc_info → 格式化异常信息
      5. ConsoleRenderer / JSONRenderer → 最终输出格式
    """
    # 添加 ISO 8601 时间戳（国际标准时间格式）
    timestamper = structlog.processors.TimeStamper(fmt="iso")

    # 所有模式共享的基础 processor
    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,  # 合并 bind() 绑定的上下文
        structlog.processors.add_log_level,       # 添加 level 字段
        timestamper,                               # 添加时间戳
    ]

    if json_format:
        # 生产模式：输出 JSON 行
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.format_exc_info,   # 异常格式化
                structlog.processors.JSONRenderer(),    # JSON 渲染器
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level.upper())
            ),
            context_class=dict[str, Any],
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,  # 性能优化：缓存 logger 实例
        )
    else:
        # 开发模式：彩色终端输出
        structlog.configure(
            processors=shared_processors
            + [
                structlog.processors.format_exc_info,          # 异常格式化
                structlog.dev.ConsoleRenderer(colors=True),    # 彩色控制台
            ],
            wrapper_class=structlog.make_filtering_bound_logger(
                getattr(logging, level.upper())
            ),
            context_class=dict[str, Any],
            logger_factory=structlog.PrintLoggerFactory(sys.stderr),
            cache_logger_on_first_use=True,
        )

    # 同时配置标准库 logging（让第三方库的日志也能被 structlog 处理）
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level.upper()),
    )


def get_logger(name: str | None = None) -> Any:  # 返回类型标注为 Any 避免 mypy strict 报错
    """获取一个 structlog logger 实例。

    参数：
      name: 模块名（通常传 __name__），可选

    返回：
      一个已绑定 module 字段的 structlog BoundLogger

    使用示例：
        from agent.logging import get_logger
        logger = get_logger(__name__)
        logger.info("agent_started", max_turns=20)
    """
    logger = structlog.get_logger(name or __name__)
    if name:
        # 绑定 module 字段，方便按模块筛选日志
        logger = logger.bind(module=name)
    return logger
