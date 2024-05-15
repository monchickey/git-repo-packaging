#!/usr/bin/env python3
# coding=utf-8
import os
import sys
import logging
import subprocess
import tarfile

import yaml

config_file = './config.yaml'

def run_command(cmd: str, capture_output=False, out_cmd=True) -> subprocess.CompletedProcess[bytes]:
    try:
        if capture_output:
            stat = subprocess.run(args=cmd,
                                  shell=True, 
                                  check=True, 
                                  capture_output=capture_output)
        else:
            stat = subprocess.run(args=cmd,
                                  shell=True, 
                                  check=True, 
                                  stderr=subprocess.STDOUT)
        if not out_cmd:
            cmd = '******'
        log.info("run command: %s completed! code: %d", cmd, stat.returncode)
        return stat
    except subprocess.CalledProcessError as e:
        if not out_cmd:
            cmd = '******'
        log.error("run command: %s, error: %s", cmd, e)
    except Exception as e:
        if not out_cmd:
            cmd = '******'
        log.error("run command: %s, error: %s", cmd, e)

here = os.path.dirname(os.path.abspath(__file__))
os.chdir(here)

log = logging.getLogger()
log_formatter = logging.Formatter(fmt='%(asctime)s - %(name)s [%(levelname)s] %(message)s')
log_handler = logging.StreamHandler()
log_handler.setFormatter(log_formatter)
log.addHandler(log_handler)
log.setLevel(logging.INFO)

with open(config_file) as f:
    configs = yaml.safe_load(f)

if not configs:
    sys.exit(0)

log.info("repo number: %d", len(configs["repos"]))

for repo in configs["repos"]:
    if not os.path.isdir(repo['dir']):
        # 目前不关心子模块
        if 'is_submodule' in repo and repo['is_submodule']:
            cmd = "git clone --recursive {} {}".format(repo['uri'], repo['dir'])
        else:
            cmd = "git clone {} {}".format(repo['uri'], repo['dir'])

        stat = run_command(cmd)
        if not stat:
            sys.exit(-1)
        if stat.returncode != 0:
            sys.exit(stat.returncode)
    
    remote = 'origin'
    if 'remote' in repo and repo['remote']:
        remote = repo['remote']

    default_branch = 'main'
    if 'branch' in repo and repo['branch']:
        default_branch = repo['branch']

    # 拉取最新的远程分支列表
    cmd = "cd {} && git remote update {} --prune".format(repo['dir'], remote)
    stat = run_command(cmd)
    if not stat:
        sys.exit(-1)
    if stat.returncode != 0:
        sys.exit(stat.returncode)
    
    # 获取远程分支列表
    # cmd = "cd %s && git branch -r | grep -v '\\->' | awk '{split($1, arr, \"/\"); print arr[2]}'" % repo['dir']
    cmd = "cd %s && git branch -r | grep -v '\\->' | awk '{print $1}'" % repo['dir']
    stat = run_command(cmd, capture_output=True)
    if not stat:
        sys.exit(-1)
    if stat.returncode != 0:
        sys.exit(stat.returncode)
    if stat.stdout:
        print(stat.stdout.decode('utf-8'))

    remote_branchs = stat.stdout.strip().decode('utf-8').split('\n')
    remote_branchs = ['/'.join(b.split('/')[1:]) for b in remote_branchs]

    # 获取本地分支列表
    cmd = "cd {} && git branch".format(repo['dir'])
    stat = run_command(cmd, capture_output=True)
    if not stat:
        sys.exit(-1)
    if stat.returncode != 0:
        sys.exit(stat.returncode)
    if stat.stdout:
        print(stat.stdout.decode('utf-8'))
    
    local_branchs = stat.stdout.strip().decode('utf-8').split('\n')

    local_branchs = list(map(lambda x : x.lstrip('*').lstrip() if x.startswith('*') else x.lstrip(), local_branchs))

    # 远程新增分支
    new_branchs = set(remote_branchs) - set(local_branchs)
    log.info("diff remote branchs: %s", new_branchs)
    for new_branch in new_branchs:
        cmd = "cd {} && git branch --track {} {}/{}".format(repo['dir'], new_branch, remote, new_branch)
        stat = run_command(cmd)
        if not stat:
            sys.exit(-1)
        if stat.returncode != 0:
            sys.exit(stat.returncode)

    # 更新所有远程分支
    for remote_branch in remote_branchs:
        cmd = "cd {} && git checkout {} && git pull {} {}".format(repo['dir'], remote_branch, remote, remote_branch)
        stat = run_command(cmd)
        if not stat:
            sys.exit(-1)
        if stat.returncode != 0:
            sys.exit(stat.returncode)
    # 选择默认分支
    cmd = "cd {} && git checkout {}".format(repo['dir'], default_branch)
    stat = run_command(cmd)
    if not stat:
        sys.exit(-1)
    if stat.returncode != 0:
        sys.exit(stat.returncode)

    # 删除本地多余的分支
    old_branchs = set(local_branchs) - set(remote_branchs)
    for old_branch in old_branchs:
        cmd = "cd {} && git branch -d {}".format(repo['dir'], old_branch)
        stat = run_command(cmd)
        if not stat:
            sys.exit(-1)
        if stat.returncode != 0:
            sys.exit(stat.returncode)

    # 拉取所有最新的标签
    cmd = "cd {} && git fetch {} --tags".format(repo['dir'], remote)
    stat = run_command(cmd)
    if not stat:
        sys.exit(-1)
    if stat.returncode != 0:
        sys.exit(stat.returncode)

    packing_configs = configs['pack']

    if packing_configs['enable']:
        out_dir = ''
        if packing_configs['target']:
            if not os.path.isdir(packing_configs['target']):
                os.makedirs(packing_configs['target'])
            out_dir = packing_configs['target']

        outfile = os.path.join(out_dir, '{}.tar.gz'.format(repo['dir']))
        if os.path.isfile(outfile):
            log.info('output tar file %s already exists! skip.', outfile)
            continue
        if packing_configs['password']:
            # 解密文件：openssl aes-128-ecb -d -k '<password>' -salt -pbkdf2 -iter 10000 -in <tar-file> | tar -zxvf -
            cmd = "tar -cvzf - {} | openssl aes-128-ecb -salt -k '{}' -pbkdf2 -iter 10000 -out {}".format(repo['dir'],
                                                                                                          packing_configs['password'],
                                                                                                          outfile)
            stat = run_command(cmd, out_cmd=False)
            if not stat:
                sys.exit(-1)
            if stat.returncode != 0:
                sys.exit(stat.returncode)
        else:
            with tarfile.open(outfile, 'w:gz') as tar:
                tar.add(repo['dir'])
        log.info("output tar file %s packing completed", outfile)
