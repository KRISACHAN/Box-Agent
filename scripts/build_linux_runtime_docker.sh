#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_version="$(sed -n 's/^version = "\([^"]*\)"/\1/p' "${repo_dir}/pyproject.toml" | head -n 1)"
version="${BOX_AGENT_RUNTIME_VERSION:-${source_version}}"
requested_arch="${1:-all}"
output_dir="${BOX_AGENT_RUNTIME_OUTPUT:-${repo_dir}/dist/runtime}"
dockerfile="${repo_dir}/docker/linux-runtime/Dockerfile"

if [[ -z "${version}" ]]; then
  echo "Could not determine Box-Agent version from pyproject.toml." >&2
  exit 1
fi

case "${requested_arch}" in
  all) docker_arches=(arm64 amd64) ;;
  arm64) docker_arches=(arm64) ;;
  x64|amd64) docker_arches=(amd64) ;;
  *)
    echo "Usage: $0 [all|arm64|x64]" >&2
    exit 2
    ;;
esac

command -v docker >/dev/null 2>&1 || {
  echo "Docker is required." >&2
  exit 1
}
docker info >/dev/null 2>&1 || {
  echo "Docker daemon is not available." >&2
  exit 1
}

mkdir -p "${output_dir}"

for docker_arch in "${docker_arches[@]}"; do
  case "${docker_arch}" in
    arm64) box_arch=arm64 ;;
    amd64) box_arch=x64 ;;
  esac
  temp_output="$(mktemp -d "${TMPDIR:-/tmp}/box-agent-runtime-${box_arch}.XXXXXX")"
  trap 'rm -rf "${temp_output}"' EXIT

  echo "Building Box-Agent ${version} for linux-${box_arch}..."
  docker buildx build \
    --platform "linux/${docker_arch}" \
    --build-arg "TARGETARCH=${docker_arch}" \
    --build-arg "BOX_AGENT_VERSION=${version}" \
    --target artifact \
    --output "type=local,dest=${temp_output}" \
    --file "${dockerfile}" \
    "${repo_dir}"

  cp "${temp_output}/box-agent-runtime-v${version}-linux-${box_arch}.tar.gz" \
     "${temp_output}/box-agent-runtime-v${version}-linux-${box_arch}.tar.gz.sha256" \
     "${output_dir}/"
  rm -rf "${temp_output}"
  trap - EXIT
done

echo "Linux runtime artifacts are in ${output_dir}"
