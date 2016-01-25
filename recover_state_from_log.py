#!/usr/bin/python3

import sys
import os
import re
import json
import subprocess
import codecs
import argparse
import tempfile

import git

branchRe = re.compile(r'^.* - Branch ([^ \t\r\n]+) at ([0-9a-fA-F]+)(, current)?.$')
def GetBranch(logLine):
    m = branchRe.match(logLine)
    if m:
        br = m.group(1)
        hash = m.group(2)
        isCurrent = m.group(3) is not None
        return { "name": br, "commit": hash, "is_current": isCurrent}

    return None

lastStateRe = re.compile(r'^.*Loaded last state at transaction ([0-9]+) as:$')
def GetTransaction(logLine):
    m = lastStateRe.match(logLine)
    if m is not None:
        return int(m.group(1))
    return None

def Restore(repoPath, branchList, transaction):
    print("Restoring state for transaction: {tr}".format(tr=transaction))
    print("branch list:")
    for br in branchList:
        print("  - Branch {br} at {hash}.{current}".format(br=br["name"], hash=br["commit"], current=' Current.' if br["is_current"] else ''))

    state = { "transaction": transaction, "branch_list": branchList }

    repo = git.open(repoPath)
    if repo is None:
        print("Failed to open git repository '{r}'".format(r=repoPath))
        return 1

    stateFilePath = None
    with tempfile.NamedTemporaryFile(mode='w+', prefix='ac2git_state_', delete=False) as stateFile:
        stateFilePath = stateFile.name
        stateFile.write(json.dumps(state))

    hashObj = repo.raw_cmd(['git', 'hash-object', '-w', stateFilePath ])
    if hashObj is None:
        raise Exception("Failed to restore state! git hash-object -w {f}, returned {r}.".format(f=stateFilePath, r=hashObj))
    else:
        os.remove(stateFilePath)

    refResult = repo.raw_cmd(['git', 'update-ref', 'refs/ac2git/state', hashObj])
    if refResult is None:
        raise Exception("Failed to restore state! git update-ref refs/ac2git/state {h}, returned {r}.".format(h=hashObj, r=refResult))
    
    return 0

def Main(argv):
    argparser = argparse.ArgumentParser(description='Processes a logfile previously generated by the ac2git.py script for restore points and optionally restores the state of a git repository to a selected point.')
    argparser.add_argument('-f', '--file', dest='file', help='The log file from which the state information will be parsed.')
    argparser.add_argument('-t', '--transaction', dest='transaction', help='The transaction, from the log file, to which the state will be restored to.')
    argparser.add_argument('-r', '--git-repo', dest='repo', help='The path to the git repository whose state will be restored.')
    args = argparser.parse_args()

    if not os.path.exists(args.file):
        print("Failed to open log file '{f}'.".format(f=args.file))
        return 1

    trList = []
    with codecs.open(args.file) as f:
        line = f.readline()
        while len(line) > 0:
            line = line.strip()
            tr = GetTransaction(line)
            if tr is not None:
                branchList = []
                line = f.readline()
                while len(line) > 0:
                    line = line.strip()
                    br = GetBranch(line)
                    if br is not None:
                        branchList.append(br)
                    else:
                        break
                    line=f.readline()
                if args.transaction is not None and int(tr) == int(args.transaction):
                    return Restore(args.repo, branchList, int(args.transaction))
                elif tr not in trList:
                    trList.append(tr)
                    print("Found transaction {tr}.".format(tr=tr))
            line = f.readline()

    if len(trList) > 0:
        print("Please choose one of the transactions listed above to restore the state to and re-run the script with the -t option.")
        return 0
    else:
        print("Found no usable transaction state information in the log file '{f}'".format(f=args.file))

    return 1

if __name__ == "__main__":
    Main(sys.argv)

