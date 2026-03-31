#!/bin/bash
# NovelMaker 개발 변경 이력을 Obsidian vault에 자동 동기화
# git post-commit hook에서 호출됨

VAULT_DIR="/Users/daegyulee/문서/NovelVault/개발 로그"
REPO_DIR="/Users/daegyulee/novelMaker"

mkdir -p "$VAULT_DIR"
cd "$REPO_DIR" || exit 1

# --- 1. 변경 이력 업데이트 ---
CHANGELOG="$VAULT_DIR/변경 이력.md"

{
    echo "# NovelMaker 개발 변경 이력"
    echo ""
    echo "> 이 문서는 커밋할 때마다 자동으로 업데이트됩니다."
    echo ""
    echo "---"

    current_date=""
    git log --reverse --format="COMMIT_START%n%H%n%ai%n%s%nCOMMIT_END" | while IFS= read -r line; do
        if [ "$line" = "COMMIT_START" ]; then
            read -r hash
            read -r date_full
            read -r subject
            read -r _end  # COMMIT_END

            day=$(echo "$date_full" | cut -d' ' -f1)
            short_hash=$(echo "$hash" | cut -c1-7)

            if [ "$day" != "$current_date" ]; then
                current_date="$day"
                echo ""
                echo "## $day"
            fi

            echo ""
            echo "### \`$short_hash\` $subject"

            files=$(git diff-tree --no-commit-id --name-only -r "$hash" 2>/dev/null | head -15)
            if [ -n "$files" ]; then
                echo "- 변경 파일:"
                echo "$files" | while IFS= read -r f; do
                    echo "  - \`$f\`"
                done
            fi
        fi
    done
} > "$CHANGELOG"

# --- 2. 프로젝트 통계 업데이트 ---
STATS="$VAULT_DIR/프로젝트 통계.md"

total_commits=$(git rev-list --count HEAD)
total_files=$(git ls-files | wc -l | tr -d ' ')
py_lines=$(git ls-files '*.py' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
ts_lines=$(git ls-files '*.ts' | xargs wc -l 2>/dev/null | tail -1 | awk '{print $1}')
last_commit_date=$(git log -1 --format="%ai" | cut -d' ' -f1)
last_commit_msg=$(git log -1 --format="%s")

cat > "$STATS" << EOF
# NovelMaker 프로젝트 통계

> 마지막 업데이트: $last_commit_date

| 항목 | 값 |
|------|-----|
| 총 커밋 수 | $total_commits |
| 총 파일 수 | $total_files |
| Python 코드 | ${py_lines:-0} 줄 |
| TypeScript 코드 | ${ts_lines:-0} 줄 |
| 마지막 커밋 | $last_commit_msg |
| 마지막 커밋 날짜 | $last_commit_date |
EOF

echo "✅ Obsidian vault에 개발 로그 동기화 완료"
