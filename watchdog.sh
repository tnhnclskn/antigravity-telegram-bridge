#!/bin/bash
LOG_FILE="/Users/tnhnclskn/Projects/antigravity-telegram-bridge/bridge.log"
NOTIFY_SCRIPT="/Users/tnhnclskn/Projects/antigravity-telegram-bridge/venv/bin/python /Users/tnhnclskn/Projects/antigravity-telegram-bridge/notify.py"

tail -Fn0 $LOG_FILE | while read line ; do
    echo "$line" | grep -i "error\|exception\|conflict"
    if [ $? = 0 ] ; then
        $NOTIFY_SCRIPT "⚠️ Bot Log Uyarısı: $line"
    fi
done
