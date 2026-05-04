#!/bin/bash
# Ed Callaghan
# All-in-one to compile and push into package repository
# October 2025; May 2026

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

project='mu2e-tracker-pi-health-tools'
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
lib="${wd}/usr/lib"
bin="${wd}/usr/bin"
etc="${wd}/etc/${project}"
log="${wd}/var/log/${project}"
syd="${wd}/etc/systemd/system"
deb="${wd}/deb"
python="${lib}/python3/dist-packages/PiHealthConnection"
postinst="${tld}/postinst"
if test -d "${wd}"; then
  exit_on_error "target directory ${wd} already exists"
fi

mkdir -p "${wd}"        || exit_on_error "failed to make target directory"
mkdir -p "${control}"   || exit_on_error "failed to make control subdirectory"
mkdir -p "${bin}"       || exit_on_error "failed to make bin subdirectory"
mkdir -p "${etc}"       || exit_on_error "failed to make etc subdirectory"
mkdir -p "${log}"       || exit_on_error "failed to make log subdirectory"
mkdir -p "${syd}"       || exit_on_error "failed to make systemd subdirectory"
mkdir -p "${python}"    || exit_on_error "failed to make python subdirectory"

server="./pi-health-server.py"
binary="${bin}/pi-health-server"
hcmodule='../Client/PiHealthConnection.py'
service='../systemd/pi-health-server.service'
starget="${syd}/pi-health-server.service"
config='./pi-health-actions.ini'
ctarget="${etc}/actions.ini"

rsync ${server} ${binary}       || exit_on_error "failed to copy binary"
rsync ${hcmodule} ${python}     || exit_on_error "failed to copy python module"
rsync ${service} ${starget}     || exit_on_error "failed to copy systemd service"
rsync ${config} ${ctarget}      || exit_on_error "failed to copy actions config"
rsync ${postinst} ${control}    || exit_on_error "failed to copy postinstall script"
echo ${commit} >"${etc}/commit" || exit_on_error "failed to cache commit hash"
sed "s,%%VERSION%%,${version}," "${template}" >"${control}/control" \
  || exit_on_error "failed to write control file"
dpkg-deb --build "${wd}" || exit_on_error "failed to build package"
