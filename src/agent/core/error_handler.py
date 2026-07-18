"""错误分类与恢复策略 —— Agent 的"报错直觉"。

这个模块的核心思想：Agent 面对错误时，不能像普通程序一样崩溃。
它需要像有经验的程序员一样，根据错误类型判断：

  "这个错我能改一下再试"  → RECOVERABLE
  "数据太大了，换个方式"    → DEGRADE
  "这个我真搞不定"          → FATAL

映射规则说明：
  - SyntaxError / TypeError / ValueError → 代码写错了，重写就行
  - NameError / KeyError / AttributeError → 需要先看看环境里有什么
  - MemoryError / TimeoutError → 任务太重，降级处理
  - PermissionError → 权限问题，Agent 解决不了，报告用户

分类器的设计原则：
  - 保守策略：未知错误全部归类为 FATAL（宁可报告用户，不盲目重试）
  - 使用 MRO 遍历：先匹配最具体的异常类型（如 FileNotFoundError），
    再向上匹配父类（如 OSError → Exception）
  - 用 ClassVar 声明类变量：告诉 mypy 这是类级别共享的，不是实例属性
"""

from __future__ import annotations

from enum import IntEnum
from typing import ClassVar


class ErrorSeverity(IntEnum):
    """错误的严重程度。

    使用 IntEnum 而非普通 Enum：
      - 可以比较大小（RECOVERABLE < DEGRADE < FATAL）
      - 可以转成整数存储到日志中
    """

    RECOVERABLE = 1  # 可以自我修复（如语法错误、变量名错误）
    DEGRADE = 2      # 需要降级处理（如内存不足、超时）
    FATAL = 3        # 无法继续（如权限问题、未知严重错误）


class RecoveryAction(IntEnum):
    """Agent 面对错误的恢复策略。

    每种策略对应了 Agent 下一步的行为：
    - REWRITE_CODE:   修改代码逻辑后重试
    - CHECK_CONTEXT:  先检查环境状态，再决定怎么改
    - SIMPLIFY_TASK:  换一个更简单的方法（如分批处理而不是全量加载）
    - REPORT:         承认搞不定，向用户说明情况
    """

    REWRITE_CODE = 1   # 修改代码后重试
    CHECK_CONTEXT = 2  # 检查环境/数据后再决定
    SIMPLIFY_TASK = 3  # 换更简单的方法
    REPORT = 4         # 无法恢复，报告用户


class ErrorClassifier:
    """将 Python 异常映射为严重程度 + 恢复策略。

    核心数据结构 _rules 是一个查找表：
      异常类型 → (严重程度, 恢复策略)

    为什么用 ClassVar 而不是普通类属性？
      ClassVar 告诉 mypy："这个属性属于类，不属于实例"。
      如果不加 ClassVar，mypy strict 模式会报错。
      而且从语义上，_rules 确实是所有 ErrorClassifier 实例共享的，
      不是某个实例独有的。

    分类决策的哲学：
      1. 语法/类型错误 → 通常是 LLM 生成的代码有 bug → Agent 可以重写
      2. 名称/属性/键错误 → 环境状态和 prompt 描述不一致 → 需要探查环境
      3. 资源耗尽 → 任务可能合理但方法不对 → 降级处理
      4. 权限/系统错误 → Agent 没有能力解决 → 告知用户
    """

    # 使用 MRO（方法解析顺序）遍历，从最具体到最通用
    # 例如 FileNotFoundError → OSError → Exception
    # 先匹配 FileNotFoundError 的规则，匹配不到才尝试 OSError 的规则

    _rules: ClassVar[dict[type[BaseException], tuple[ErrorSeverity, RecoveryAction]]] = {
        # --- 可恢复：代码需要修改 ---
        # 这些错误说明 LLM 生成的代码有问题，但修改后大概率能成功
        SyntaxError:        (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        IndentationError:   (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        TypeError:          (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        ValueError:         (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        ZeroDivisionError:  (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),
        IndexError:         (ErrorSeverity.RECOVERABLE, RecoveryAction.REWRITE_CODE),

        # --- 可恢复：需要先检查环境 ---
        # 这些错误说明代码逻辑可能没错，但环境状态和预期不一致
        # 例如：CSV 里没有 "date" 列，或者 pandas 还没 import
        NameError:          (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        KeyError:           (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        AttributeError:     (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        ImportError:        (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        ModuleNotFoundError:(ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),
        FileNotFoundError:  (ErrorSeverity.RECOVERABLE, RecoveryAction.CHECK_CONTEXT),

        # --- 降级：任务太重 ---
        # 这些错误说明"方法对了，但规模不对"——需要简化
        MemoryError:        (ErrorSeverity.DEGRADE,     RecoveryAction.SIMPLIFY_TASK),
        TimeoutError:       (ErrorSeverity.DEGRADE,     RecoveryAction.SIMPLIFY_TASK),
        RecursionError:     (ErrorSeverity.DEGRADE,     RecoveryAction.SIMPLIFY_TASK),

        # --- 致命：超出能力范围 ---
        # 权限问题 Agent 无法解决（它没有 sudo）
        PermissionError:    (ErrorSeverity.FATAL,       RecoveryAction.REPORT),
    }

    @classmethod
    def classify(cls, error: BaseException) -> tuple[ErrorSeverity, RecoveryAction]:
        """将一个异常分类，返回 (严重程度, 恢复策略)。

        遍历异常的 MRO 链来查找最匹配的规则。
        如果找不到匹配，返回 (FATAL, REPORT) —— 宁可保守也不盲目乐观。

        MRO 遍历示例：
          FileNotFoundError.__mro__ = (
              FileNotFoundError,   → 先匹配这个
              OSError,             → 再匹配这个
              Exception,           → 最后匹配这个
              BaseException,
              object
          )
          如果没有 FileNotFoundError 的专门规则，
          就退而求其次匹配 OSError 的规则。

        Args:
            error: 需要分类的异常对象

        Returns:
            (ErrorSeverity, RecoveryAction) 元组
        """
        for exc_type in type(error).__mro__:
            if exc_type in cls._rules:
                return cls._rules[exc_type]

        # 未知错误 → 保守策略：报告用户
        return (ErrorSeverity.FATAL, RecoveryAction.REPORT)
