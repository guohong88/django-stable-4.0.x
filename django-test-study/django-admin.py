# !/usr/bin/env python
# -*-coding:utf-8 -*-

"""
# File       : test_commmand.py
# Time       ：2023/10/18 23:58
# Author     ：author luoghong
# version    ：python 3.10
# Description：
dango-admin.py startproject django_frist
命令行源码解析
"""

# execute_from_command_line
import re
import sys
from django.core.management import execute_from_command_line

if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\.pyw|\.exe)?$', "", sys.argv[0])
    sys.exit(execute_from_command_line())
