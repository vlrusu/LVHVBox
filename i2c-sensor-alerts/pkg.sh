#!/bin/bash

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

project='mu2e-tracker-i2c-sensor-alerts'
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

tld="${PWD}/deb"
template="${tld}/control-template"
wd="${tld}/${label}"
control="${wd}/DEBIAN"
bin="${wd}/usr/bin"
etc="${wd}/etc/${project}"
log="${wd}/var/log/mu2e-tracker-i2c-sensor-tools"
syd="${wd}/etc/systemd/system"
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

server="./i2c-sensor-alerts.py"
binary="${bin}/i2c-sensor-alerts"
service='../systemd/i2c-sensor-alerts.service'
starget="${syd}/i2c-sensor-alerts.service"
envfile='./i2c-sensor-alerts.env'
etarget="${etc}/i2c-sensor-alerts.env"

rsync ${server} ${binary}       || exit_on_error "failed to copy binary"
rsync ${service} ${starget}     || exit_on_error "failed to copy systemd service"
rsync ${envfile} ${etarget}     || exit_on_error "failed to copy env file"
rsync ${postinst} ${control}    || exit_on_error "failed to copy postinstall script"
echo ${commit} >"${etc}/commit" || exit_on_error "failed to cache commit hash"
sed "s,%%VERSION%%,${version}," "${template}" >"${control}/control" \
  || exit_on_error "failed to write control file"
dpkg-deb --build "${wd}" || exit_on_error "failed to build package"
