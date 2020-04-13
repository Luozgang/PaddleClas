#   Copyright (c) 2020 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import os
import requests
import shutil
import tarfile
import tqdm
import zipfile

from ppcls.utils.check import check_architecture
from ppcls.utils import logger

__all__ = ['get']

DOWNLOAD_RETRY_LIMIT = 3


class UrlError(Exception):
    """ UrlError
    """

    def __init__(self, url='', code=''):
        message = "Downloading from {} failed with code {}!".format(url, code)
        super(UrlError, self).__init__(message)


class RetryError(Exception):
    """ RetryError
    """

    def __init__(self, url='', times=''):
        message = "Download from {} failed. Retry({}) limit reached".format(
            url, times)
        super(RetryError, self).__init__(message)


def _get_url(architecture):
    prefix = "https://paddle-imagenet-models-name.bj.bcebos.com/"
    fname = architecture + "_pretrained.tar"
    return prefix + fname


def _move_and_merge_tree(src, dst):
    """
    Move src directory to dst, if dst is already exists,
    merge src to dst
    """
    if not os.path.exists(dst):
        shutil.move(src, dst)
    elif os.path.isfile(src):
        shutil.move(src, dst)
    else:
        for fp in os.listdir(src):
            src_fp = os.path.join(src, fp)
            dst_fp = os.path.join(dst, fp)
            if os.path.isdir(src_fp):
                if os.path.isdir(dst_fp):
                    _move_and_merge_tree(src_fp, dst_fp)
                else:
                    shutil.move(src_fp, dst_fp)
            elif os.path.isfile(src_fp) and \
                    not os.path.isfile(dst_fp):
                shutil.move(src_fp, dst_fp)


def _download(url, path):
    """
    Download from url, save to path.
    url (str): download url
    path (str): download to given path
    """
    if not os.path.exists(path):
        os.makedirs(path)

    fname = os.path.split(url)[-1]
    fullname = os.path.join(path, fname)
    retry_cnt = 0

    while not os.path.exists(fullname):
        if retry_cnt < DOWNLOAD_RETRY_LIMIT:
            retry_cnt += 1
        else:
            raise RetryError(url, DOWNLOAD_RETRY_LIMIT)

        logger.info("Downloading {} from {}".format(fname, url))

        req = requests.get(url, stream=True)
        if req.status_code != 200:
            raise UrlError(url, req.status_code)

        # For protecting download interupted, download to
        # tmp_fullname firstly, move tmp_fullname to fullname
        # after download finished
        tmp_fullname = fullname + "_tmp"
        total_size = req.headers.get('content-length')
        with open(tmp_fullname, 'wb') as f:
            if total_size:
                for chunk in tqdm.tqdm(
                        req.iter_content(chunk_size=1024),
                        total=(int(total_size) + 1023) // 1024,
                        unit='KB'):
                    f.write(chunk)
            else:
                for chunk in req.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        shutil.move(tmp_fullname, fullname)

    return fullname


def _decompress(fname):
    """
    Decompress for zip and tar file
    """
    logger.info("Decompressing {}...".format(fname))

    # For protecting decompressing interupted,
    # decompress to fpath_tmp directory firstly, if decompress
    # successed, move decompress files to fpath and delete
    # fpath_tmp and remove download compress file.
    fpath = os.path.split(fname)[0]
    fpath_tmp = os.path.join(fpath, 'tmp')
    if os.path.isdir(fpath_tmp):
        shutil.rmtree(fpath_tmp)
        os.makedirs(fpath_tmp)

    if fname.find('tar') >= 0:
        with tarfile.open(fname) as tf:
            tf.extractall(path=fpath_tmp)
    elif fname.find('zip') >= 0:
        with zipfile.ZipFile(fname) as zf:
            zf.extractall(path=fpath_tmp)
    else:
        raise TypeError("Unsupport compress file type {}".format(fname))

    for f in os.listdir(fpath_tmp):
        src_dir = os.path.join(fpath_tmp, f)
        dst_dir = os.path.join(fpath, f)
        _move_and_merge_tree(src_dir, dst_dir)

    shutil.rmtree(fpath_tmp)
    os.remove(fname)


def get(architecture, path, decompress=True):
    """
    Get the pretrained model.

    Args:
        architecture: the name of which architecture to get. 
            If the name is not exist, will raises UrlError with error code 404.
        path: which dir to save the pretrained model.
        decompress: decompress the download or not.

    Raises:
        RetryError or UrlError if download failed
    """
    url = _get_url(architecture)
    fname = _download(url, path)
    if decompress: _decompress(fname)
    logger.info("download {} finished ".format(fname))
