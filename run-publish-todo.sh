#!/bin/bash
set -e
chmod +x ~/publish-todo.sh
sha256sum ~/todo.phext.new
~/publish-todo.sh
