#!/bin/sh
# 安装 Dock Panel。
#
# 服务器一键安装（GitHub Release）：
#   curl -fsSL https://github.com/OptLTD/dock-panel/releases/latest/download/install.sh | sudo sh
#
# 指定版本：
#   curl -fsSL https://github.com/OptLTD/dock-panel/releases/latest/download/install.sh | sudo sh -s -- --version 0.1.0
#
# 也可在 make dist 解压后的目录里直接执行 ./install.sh
set -eu

REPO="${DOCK_PANEL_REPO:-OptLTD/dock-panel}"
PREFIX="${PREFIX:-/usr}"
DESTDIR="${DESTDIR:-}"
VERSION="${DOCK_PANEL_VERSION:-latest}"

usage() {
  echo "用法: $0 [--version <ver>] [--repo owner/name] [--prefix /usr]" >&2
}

while [ $# -gt 0 ]; do
  case "$1" in
    --version|-v)
      VERSION="${2#v}"
      shift 2
      ;;
    --repo)
      REPO="$2"
      shift 2
      ;;
    --prefix)
      PREFIX="$2"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    v[0-9]*|[0-9]*.[0-9]*)
      VERSION="${1#v}"
      shift
      ;;
    *)
      echo "未知参数: $1" >&2
      usage
      exit 1
      ;;
  esac
done

install_tree() {
  ROOT="$1"
  COCKPITDIR="${DESTDIR}${PREFIX}/share/cockpit/dock-panel"
  LIBEXECDIR="${DESTDIR}${PREFIX}/libexec/dock-panel"
  STATEDIR="${DESTDIR}/var/lib/dock-panel"

  if [ ! -f "$ROOT/cockpit/manifest.json" ]; then
    echo "找不到 $ROOT/cockpit/manifest.json" >&2
    exit 1
  fi
  if [ ! -f "$ROOT/backend/cli.py" ] || [ ! -d "$ROOT/backend/src" ]; then
    echo "找不到 $ROOT/backend/cli.py 或 backend/src" >&2
    exit 1
  fi

  install -d "$COCKPITDIR" "$LIBEXECDIR" "$STATEDIR/certs" "$STATEDIR/projects"
  cp -a "$ROOT/cockpit/." "$COCKPITDIR/"
  rm -rf "$LIBEXECDIR/src"
  cp -a "$ROOT/backend/cli.py" "$LIBEXECDIR/cli.py"
  cp -a "$ROOT/backend/src" "$LIBEXECDIR/src"
  chmod 0755 "$LIBEXECDIR/cli.py"
  find "$LIBEXECDIR" -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

  echo "已安装:"
  echo "  前端  $COCKPITDIR"
  echo "  后端  $LIBEXECDIR"
  echo "打开 Cockpit 侧栏「Dock Panel」。若未出现，执行: systemctl restart cockpit"
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "缺少命令: $1" >&2
    exit 1
  fi
}

if [ "$(id -u)" -ne 0 ]; then
  echo "请使用 root 或 sudo 安装" >&2
  exit 1
fi

# 从解压后的发布包目录执行时，直接安装本地文件
if [ -f "$0" ]; then
  SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
  if [ -f "$SCRIPT_DIR/cockpit/manifest.json" ]; then
    install_tree "$SCRIPT_DIR"
    exit 0
  fi
fi

need_cmd curl
need_cmd tar
need_cmd mktemp
need_cmd install

if [ "$VERSION" = "latest" ]; then
  URL="https://github.com/${REPO}/releases/latest/download/dock-panel.tar.gz"
else
  URL="https://github.com/${REPO}/releases/download/v${VERSION}/dock-panel-${VERSION}.tar.gz"
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT INT TERM

echo "下载 $URL"
CURL_AUTH=""
if [ -n "${GITHUB_TOKEN:-}" ]; then
  CURL_AUTH="${GITHUB_TOKEN}"
elif [ -n "${GH_TOKEN:-}" ]; then
  CURL_AUTH="${GH_TOKEN}"
fi

if [ -n "$CURL_AUTH" ]; then
  if ! curl -fL --retry 3 -H "Authorization: Bearer ${CURL_AUTH}" -H "Accept: application/octet-stream" -o "$TMP/dock-panel.tar.gz" "$URL"; then
    echo "下载失败。若仓库是私有的，请设置 GH_TOKEN；并确认已发布 Release。" >&2
    exit 1
  fi
else
  if ! curl -fL --retry 3 -o "$TMP/dock-panel.tar.gz" "$URL"; then
    echo "下载失败。请确认仓库已打 tag 并成功跑通 GitHub Actions Release。" >&2
    echo "例如: git tag v0.1.0 && git push origin v0.1.0" >&2
    exit 1
  fi
fi

tar -xzf "$TMP/dock-panel.tar.gz" -C "$TMP"
MANIFEST="$(find "$TMP" -maxdepth 3 -path '*/cockpit/manifest.json' | head -n 1)"
if [ -z "$MANIFEST" ]; then
  echo "压缩包里没有 cockpit/manifest.json" >&2
  exit 1
fi
install_tree "$(dirname "$(dirname "$MANIFEST")")"
