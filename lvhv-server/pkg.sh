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

project='mu2e-tracker-lvhv-tools'
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
syd="${wd}/etc/systemd/system"
deb="${wd}/deb"
python="${lib}/python3/dist-packages/PowerSupplyServerConnection"
postinst="${tld}/postinst"
if test -d "${wd}"; then
  exit_on_error "target directory ${wd} already exists"
fi

mkdir -p "${wd}"        || exit_on_error "failed to make target directory"
mkdir -p "${control}"   || exit_on_error "failed to make control subdirectory"
mkdir -p "${bin}"       || exit_on_error "failed to make bin subdirectory"
mkdir -p "${etc}"       || exit_on_error "failed to make etc subdirectory"
mkdir -p "${syd}"       || exit_on_error "failed to make systemd subdirectory"
mkdir -p "${python}"    || exit_on_error "failed to make python subdirectory"

tmp="$(mktemp --directory)"
binary="${tmp}/lvhv-server"
header="../commands.h"
psmodule='../Client/PowerSupplyServerConnection.py'
hvmodule='../Client/WireAnalogDigitalConversion.py'
hvdac='../Client/nominal-hv-dac-calibration.json'
client='../Client/Client.py'
gui='../Client/gui.py'
service='../systemd/lvhv-server.service'
desktop='../systemd/lvhv-gui.desktop'
ctarget="${bin}/lvhv-client"
gtarget="${bin}/lvhv-gui"
starget="${syd}/lvhv-server.service"
dtarget="${etc}/lvhv-gui.desktop"
pushd ${tmp} || exit_on_error "failed to cd to ${tmp}"
cmake ${pd}  || exit_on_error "cmake failed"
make         || exit_on_error "compilation failed"
popd
rsync ${binary} ${bin}          || exit_on_error "failed to copy binary"
rsync ${header} ${etc}          || exit_on_error "failed to copy command header"
rsync ${psmodule} ${python}     || exit_on_error "failed to copy python module"
rsync ${hvmodule} ${python}     || exit_on_error "failed to copy python module"
rsync ${hvdac} ${etc}           || exit_on_error "failed to copy hv dac calibration"
rsync ${client} ${ctarget}      || exit_on_error "failed to copy python client"
rsync ${gui} ${gtarget}         || exit_on_error "failed to copy gui monitor"
rsync ${service} ${starget}     || exit_on_error "failed to copy systemd service"
rsync ${desktop} ${dtarget}     || exit_on_error "failed to copy gui desktop entry"
rsync ${postinst} ${control}    || exit_on_error "failed to copy postinstall script"
rm -rf ${tmp}
echo ${commit} >"${etc}/commit" || exit_on_error "failed to cache commit hash"
sed "s,%%VERSION%%,${version}," "${template}" >"${control}/control" \
  || exit_on_error "failed to write control file"
dpkg-deb --build "${wd}" || exit_on_error "failed to build package"
