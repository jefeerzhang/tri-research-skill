#!/bin/bash
# tri-research state machine — 强制状态管理
# 用法: bash state_machine.sh <command> [args]
# 命令:
#   init <research_id>     — 初始化研究状态（S0）
#   check                  — 检查当前状态
#   advance <phase>        — 推进到下一阶段
#   get_phase              — 获取当前阶段
#   is_phase_done <phase>  — 检查某阶段是否已完成
#   get_params             — 获取确认后的参数
#   set_params <json>      — 设置确认后的参数

RESEARCH_DIR="${TRI_RESEARCH_HOME:-$HOME/.tri-research}"

# 确保目录存在
mkdir -p "$RESEARCH_DIR"

# 命令分发
case "$1" in
    init)
        # 初始化一个新的研究会话
        RESEARCH_ID="${2:-$(date +%s)}"
        STATE_FILE="$RESEARCH_DIR/${RESEARCH_ID}.state"
        PARAMS_FILE="$RESEARCH_DIR/${RESEARCH_ID}.params"

        # 如果已存在，先清理
        rm -f "$STATE_FILE" "$PARAMS_FILE"

        # 初始化状态为 S0
        echo "S0" > "$STATE_FILE"
        echo "INIT" >> "$STATE_FILE"
        echo "$(date -Iseconds)" >> "$STATE_FILE"

        echo "OK:Initialized research session $RESEARCH_ID"
        echo "STATE:S0"
        echo "MESSAGE:研究会话已初始化。Phase 0 CLARIFY 等待用户确认。"
        ;;

    check)
        # 检查当前状态（读取最近的状态文件）
        STATE_FILE=$(ls -t "$RESEARCH_DIR"/*.state 2>/dev/null | head -1)
        if [ -z "$STATE_FILE" ]; then
            echo "STATE:S0"
            echo "MESSAGE:没有活跃的研究会话。请先 init。"
            exit 0
        fi

        PHASE=$(head -1 "$STATE_FILE")
        echo "STATE:$PHASE"
        echo "FILE:$STATE_FILE"

        case "$PHASE" in
            S0) echo "MESSAGE:Phase 0 CLARIFY 等待用户确认。不要派发子代理。" ;;
            S1) echo "MESSAGE:Phase 1-3 已完成。可以派发子代理（S2）。" ;;
            S2) echo "MESSAGE:子代理已派发。等待结果后进入 S3。不要重复派发。" ;;
            S3) echo "MESSAGE:综合阶段。子代理已返回。可以写报告。" ;;
            DONE) echo "MESSAGE:研究已完成。不要重新开始。" ;;
        esac
        ;;

    advance)
        # 推进到下一阶段
        RESEARCH_ID="${2:-$(date +%s)}"
        STATE_FILE=$(ls -t "$RESEARCH_DIR"/*.state 2>/dev/null | head -1)

        if [ -z "$STATE_FILE" ]; then
            echo "ERROR:没有活跃的研究会话"
            exit 1
        fi

        CURRENT=$(head -1 "$STATE_FILE")
        NEXT="$2"

        # 状态机规则
        case "$CURRENT" in
            S0)
                if [ "$NEXT" = "S1" ]; then
                    echo "S1" > "$STATE_FILE"
                    echo "INIT" >> "$STATE_FILE"
                    echo "$(date -Iseconds)" >> "$STATE_FILE"
                    echo "OK:已推进到 S1（Phase 1-3: 评估与规划）"
                    echo "STATE:S1"
                else
                    echo "ERROR:从 S0 只能推进到 S1"
                    exit 1
                fi
                ;;
            S1)
                if [ "$NEXT" = "S2" ]; then
                    echo "S2" > "$STATE_FILE"
                    echo "SUBAGENTS_DISPATCHED" >> "$STATE_FILE"
                    echo "$(date -Iseconds)" >> "$STATE_FILE"
                    echo "OK:已推进到 S2（派发子代理）。不要重复派发。"
                    echo "STATE:S2"
                else
                    echo "ERROR:从 S1 只能推进到 S2"
                    exit 1
                fi
                ;;
            S2)
                if [ "$NEXT" = "S3" ]; then
                    echo "S3" > "$STATE_FILE"
                    echo "SUBAGENTS_RETURNED" >> "$STATE_FILE"
                    echo "$(date -Iseconds)" >> "$STATE_FILE"
                    echo "OK:已推进到 S3（综合报告）。子代理结果已接收。"
                    echo "STATE:S3"
                else
                    echo "ERROR:从 S2 只能推进到 S3"
                    exit 1
                fi
                ;;
            S3)
                if [ "$NEXT" = "DONE" ]; then
                    echo "DONE" > "$STATE_FILE"
                    echo "REPORT_WRITTEN" >> "$STATE_FILE"
                    echo "$(date -Iseconds)" >> "$STATE_FILE"
                    echo "OK:研究已完成。报告已生成。"
                    echo "STATE:DONE"
                else
                    echo "ERROR:从 S3 只能推进到 DONE"
                    exit 1
                fi
                ;;
            DONE)
                echo "ERROR:研究已完成。不要重新开始。"
                exit 1
                ;;
        esac
        ;;

    get_phase)
        STATE_FILE=$(ls -t "$RESEARCH_DIR"/*.state 2>/dev/null | head -1)
        if [ -z "$STATE_FILE" ]; then
            echo "S0"
        else
            head -1 "$STATE_FILE"
        fi
        ;;

    is_phase_done)
        # 检查某阶段是否已完成
        PHASE="$2"
        STATE_FILE=$(ls -t "$RESEARCH_DIR"/*.state 2>/dev/null | head -1)
        if [ -z "$STATE_FILE" ]; then
            echo "NO"
            exit 0
        fi

        CURRENT=$(head -1 "$STATE_FILE")
        case "$PHASE" in
            S0) [ "$CURRENT" != "S0" ] && echo "YES" || echo "NO" ;;
            S1) [ "$CURRENT" = "S1" ] || [ "$CURRENT" = "S2" ] || [ "$CURRENT" = "S3" ] || [ "$CURRENT" = "DONE" ] && echo "YES" || echo "NO" ;;
            S2) [ "$CURRENT" = "S2" ] || [ "$CURRENT" = "S3" ] || [ "$CURRENT" = "DONE" ] && echo "YES" || echo "NO" ;;
            S3) [ "$CURRENT" = "S3" ] || [ "$CURRENT" = "DONE" ] && echo "YES" || echo "NO" ;;
            *) echo "NO" ;;
        esac
        ;;

    get_params)
        PARAMS_FILE=$(ls -t "$RESEARCH_DIR"/*.params 2>/dev/null | head -1)
        if [ -z "$PARAMS_FILE" ]; then
            echo "ERROR:没有参数文件"
            exit 1
        fi
        cat "$PARAMS_FILE"
        ;;

    set_params)
        PARAMS_FILE=$(ls -t "$RESEARCH_DIR"/*.params 2>/dev/null | head -1)
        if [ -z "$PARAMS_FILE" ]; then
            # 创建新参数文件
            PARAMS_FILE="$RESEARCH_DIR/$(date +%s).params"
        fi
        echo "$2" > "$PARAMS_FILE"
        echo "OK:参数已设置"
        ;;

    *)
        echo "用法: bash state_machine.sh <command> [args]"
        echo "命令: init, check, advance, get_phase, is_phase_done, get_params, set_params"
        exit 1
        ;;
esac
