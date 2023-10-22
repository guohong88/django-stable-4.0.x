# !/usr/bin/env python
# -*-coding:utf-8 -*-

"""
# File       : views.py
# Time       ：2023/10/19 0:34
# Author     ：author luoghong
# version    ：python 3.10
# Description：
"""
from django.http.response import HttpResponse


def echo(request, *args, **kwargs):
    data = request.GET
    value = data.get("name", 'word')
    return HttpResponse(value, content_type='text/plain')
