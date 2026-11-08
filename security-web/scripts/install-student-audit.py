#!/usr/bin/env python3
"""Install isolated PBL4 services. Does NOT start them, cut over .env, or touch SSHFS."""
import argparse, datetime, grp, os, pathlib, pwd, shutil, stat, subprocess, sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
def run(*args): subprocess.run(args,check=True)
def main():
    p=argparse.ArgumentParser();p.add_argument('role',choices=['sender','receiver']);p.add_argument('--install-packages',action='store_true');p.add_argument('--backend-user',default='dinh-huynh-nguyen-khang');a=p.parse_args()
    if os.geteuid()!=0: sys.exit('Run with sudo; no files changed.')
    user=pwd.getpwnam('khang1901' if a.role=='sender' else a.backend_user)
    needed=['rsyslog','rsyslog-relp','logrotate']
    missing=[]
    for name in needed:
        r=subprocess.run(['dpkg-query','-W','-f=${Status}',name],capture_output=True,text=True)
        if r.returncode or r.stdout.strip()!='install ok installed':missing.append(name)
    if missing:
        if not a.install_packages:sys.exit('Missing packages: '+', '.join(missing)+'; rerun with --install-packages to install only these.')
        run('apt-get','install','--no-install-recommends','-y',*missing)
    writer=pwd.getpwnam('khang1901' if a.role=='sender' else 'syslog')
    group=grp.getgrgid(user.pw_gid).gr_name
    if a.role=='sender':
        source=pathlib.Path('/home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log')
        run('runuser','-u',writer.pw_name,'--','test','-r',str(source))
        if not source.is_file() or source.is_symlink() or source.stat().st_uid!=writer.pw_uid:sys.exit('Unexpected source owner/type; refusing.')
        print('Source bytes:',source.stat().st_size,'mode:',oct(stat.S_IMODE(source.stat().st_mode)))
        print('Source directory owner/mode:',source.parent.stat().st_uid,oct(stat.S_IMODE(source.parent.stat().st_mode)))
        if list(source.parent.glob('student-audit.log*.gz')):sys.exit('Compressed generations present; review sender input scope before installing.')
        run('runuser','-u',writer.pw_name,'--','python3',str(ROOT/'scripts/verify-student-audit-forwarding.py'),'--source',str(source))
    stamp=datetime.datetime.now().strftime('%Y%m%dT%H%M%S%f')
    backup=pathlib.Path('/etc/pbl4/backups')/('audit-'+a.role+'-'+stamp)
    def safe(path):
        for item in [path,*path.parents]:
            if item.is_symlink():sys.exit('Refusing symlink: '+str(item))
    safe(backup);backup.mkdir(parents=True,mode=0o700);os.chmod(backup,0o700)
    def put(path,data,mode=0o644):
        dest=pathlib.Path(path);safe(dest)
        if dest.exists():
            if not dest.is_file():sys.exit('Not a regular file: '+path)
            old=backup/str(dest).lstrip('/');old.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,old)
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(data);os.chown(dest,0,0);os.chmod(dest,mode)
    def directory(path,uid,gid,mode):
        d=pathlib.Path(path);safe(d)
        if d.exists():
            if not d.is_dir() or d.stat().st_uid!=uid or d.stat().st_gid!=gid or stat.S_IMODE(d.stat().st_mode)!=mode:
                sys.exit('Existing directory ownership/mode differs; inspect before installation: '+path)
        else:d.mkdir(parents=True,mode=mode);os.chown(d,uid,gid);os.chmod(d,mode)
    directory('/var/lib/pbl4-audit-rotation',0,0,0o700)
    state='/var/lib/pbl4-audit-'+a.role
    directory(state,writer.pw_uid,user.pw_gid,0o700)
    if a.role=='receiver':
        directory('/var/log/pbl4',writer.pw_uid,user.pw_gid,0o750)
        directory('/var/lib/pbl4-audit-guard',0,0,0o700)
        put('/usr/local/libexec/pbl4-audit-guard',(ROOT/'deploy/rsyslog/pbl4-audit-guard').read_text(),0o755)
    profile=pathlib.Path('/etc/apparmor.d/usr.sbin.rsyslogd')
    if profile.exists():
        if 'include if exists <rsyslog.d>' not in profile.read_text():
            sys.exit('AppArmor profile lacks rsyslog.d include; needs reviewed local policy before proceeding.')
        policy=f"/etc/pbl4/audit/{a.role}.conf r,\n/var/lib/pbl4-audit-{a.role}/ r,\n/var/lib/pbl4-audit-{a.role}/** rwk,\n/run/pbl4-audit-{a.role}/ r,\n/run/pbl4-audit-{a.role}/** rwk,\n"
        if a.role=='sender':
            policy+='/home/khang1901/idps-web-aws/student-web/backend/logs/ r,\n/home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log* r,\n'
        put('/etc/apparmor.d/rsyslog.d/pbl4-audit-'+a.role,policy)
        run('apparmor_parser','-r',str(profile))
    config=(ROOT/f'deploy/rsyslog/student-audit-{a.role}.conf').read_text()
    put('/etc/pbl4/audit/'+a.role+'.conf',config)
    run('runuser','-u',writer.pw_name,'--','/usr/sbin/rsyslogd','-N1','-f','/etc/pbl4/audit/'+a.role+'.conf')
    unit=(ROOT/f'deploy/rsyslog/pbl4-audit-{a.role}.service').read_text().replace('@BACKEND_GROUP@',group)
    put('/etc/systemd/system/pbl4-audit-'+a.role+'.service',unit)
    log='/home/khang1901/idps-web-aws/student-web/backend/logs/student-audit.log' if a.role=='sender' else '/var/log/pbl4/student-audit.log'
    mode='0600' if a.role=='sender' else '0640'
    rotation=f'''{log} {{
    daily
    maxsize 16M
    rotate -1
    missingok
    notifempty
    nocompress
    su {writer.pw_name} {group}
    create {mode} {writer.pw_name} {group}
'''
    if a.role=='receiver':rotation+='    postrotate\n        /bin/systemctl reload pbl4-audit-receiver.service\n    endscript\n'
    rotation+='}\n'
    put('/etc/pbl4/audit/'+a.role+'.logrotate',rotation)
    run('/usr/sbin/logrotate','--debug','/etc/pbl4/audit/'+a.role+'.logrotate')
    rotate_name='pbl4-audit-'+a.role+'-rotate'
    put('/etc/systemd/system/'+rotate_name+'.service',f'''[Unit]
Description=Rotate PBL4 {a.role} audit only
[Service]
Type=oneshot
ExecStart=/usr/sbin/logrotate -s /var/lib/pbl4-audit-rotation/{a.role}.state /etc/pbl4/audit/{a.role}.logrotate
''')
    put('/etc/systemd/system/'+rotate_name+'.timer',f'''[Unit]
Description=Check PBL4 {a.role} audit size every minute
[Timer]
OnBootSec=60
OnUnitActiveSec=60
AccuracySec=5
[Install]
WantedBy=timers.target
''')
    run('systemd-analyze','verify','/etc/systemd/system/pbl4-audit-'+a.role+'.service','/etc/systemd/system/'+rotate_name+'.service','/etc/systemd/system/'+rotate_name+'.timer')
    run('systemctl','daemon-reload')
    print('Installed, NOT started/enabled. Backups:',backup)
    print('Review docs then: sudo systemctl enable --now pbl4-audit-'+a.role+'.service '+rotate_name+'.timer')
if __name__=='__main__':main()
