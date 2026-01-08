#!/bin/bash
# Ed Callaghan
# All-in-one to compile and push into package repository
# October 2025

exit_on_error(){
  msg="${1}"
  echo "${this} error: ${msg}" >&2
  exit 1
}
this="$(basename ${0})"

print_usage(){
  echo "usage: ${this} major minor patch"
  exit 2
}

project='mu2e-tracker-pico-smartswitch-applications'
commit=$(git rev-parse HEAD)

if ! test ${#} -eq 3; then
  print_usage
fi

source /etc/os-release
codename="${VERSION_CODENAME}"

major="${1}"
minor="${2}"
patch="${3}"
version="${major}.${minor}.${patch}"
vstring="v${major}_${minor}_${patch}"
label="${project}_${codename}_${vstring}"

pd="${PWD}"
tld="${PWD}/deb"
template="${tld}/control-template"
wd="${tld}/${label}"
control="${wd}/DEBIAN"
etc="${wd}/etc/${project}"
deb="${wd}/deb"
if test -d "${wd}"; then
  exit_on_error "target directory ${wd} already exists"
fi

mkdir -p "${wd}"        || exit_on_error "failed to make target directory"
mkdir -p "${control}"   || exit_on_error "failed to make control subdirectory"
mkdir -p "${etc}"       || exit_on_error "failed to make etc subdirectory"

pico_sdk="${HOME}/sw/mu2e-tracker-picotool/pico-sdk"
export PICO_SDK_PATH="${pico_sdk}"

tmp="$(mktemp --directory)"
firmware_1="${tmp}/SmartSwitch_1.elf"
firmware_2="${tmp}/SmartSwitch_2.elf"
pushd ${tmp} || exit_on_error "failed to cd to ${tmp}"
cmake ${pd}  || exit_on_error "cmake failed"
make         || exit_on_error "compilation failed"
popd
rsync ${firmware_1} ${etc} || exit_on_error "failed to copy firmware (1)"
rsync ${firmware_2} ${etc} || exit_on_error "failed to copy firmware (2)"
rm -rf ${tmp}
echo ${commit} >"${etc}/commit" || exit_on_error "failed to cache commit hash"
sed "s,%%VERSION%%,${version}," "${template}" >"${control}/control" \
  || exit_on_error "failed to write control file"
dpkg-deb --build "${wd}" || exit_on_error "failed to build package"
