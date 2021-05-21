# -*- coding: utf-8 -*-
"""
Created on Fri May 21 14:10:09 2021

Sync files from Python's simple HTTP server

@author: Ronan
"""
### Imports
# Standard library imports
from __future__ import division, unicode_literals, print_function

import sys
import os
import os.path as osp
import argparse
import errno
import time
import logging
from pathlib import Path
from urllib.parse import urljoin

# 3rd-party imports
import requests
from bs4 import BeautifulSoup

# 1st-party imports

#%% Module-level data
IGNORE = sorted(['thumbs.db', 'desktop.ini'])


#%% Top-level functions
def mkdir_p(path):
    """Creates a directory and parent directories if needed

    Parameters:
        path: str
            Path of the bottom-most directory to create
    """
    try:
        os.makedirs(path)
    except OSError as exc:  # Python >2.5, to catch possible race condition
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else:
            raise


def sync(url, path='.', loop=0, ignore=IGNORE):
    if loop < 0:
        raise ValueError("Loop must not be negative!")
    path = Path(path)
    if not path.is_dir():
        raise ValueError("Path must be an existing directory.")
    session = requests.Session()
    d = Dir(url, path, ignore, session)
    d.update()

    if loop == 0:
        return
    while True:
        try:
            time.sleep(loop)
        except KeyboardInterrupt:
            break


#%% Classes
class File():
    def __init__(self, url, path, session=None):
        self.url = url
        self.path = path
        self.session = session
        self.status = "pending"

    def update(self):
        h = self.session.head(self.url)
        size = int(h.headers.get('Content-Length'))
        if self.path.exists() and self.path.stat().st_size == size:
            logging.info(f"File { self.path } is current")
            self.status = 'updated'
            return

        logging.info(f"Downloading { self.url }")
        r = self.session.get(self.url)
        if r.status_code != 200:
            logging.error(f"Error downloading from { self.url } "
                          f"(status code { r.status_code })")
            self.status = 'error'
            return
        self.path.write_bytes(r.content)
        self.status = 'updated'

    def __repr__(self):
        return f'File({self.path}, {self.status})'


class Dir():
    def __init__(self, url, path, ignore, session=None):
        self.url = url
        self.path = path
        self.ignore = [ign.lower() for ign in ignore]
        self.session = session
        self.status = "pending"
        self.children = {}
        # self.update()

    def update(self):
        self.status = 'updating'
        session = self.session or requests
        # Get directory listing from server
        r = session.get(self.url)
        if r.status_code != 200:
            logging.error(f"Error downloading from { self.url } "
                          f"(status code { r.status_code })")
            self.status = 'error'
            return

        # Create directory
        if not self.path.exists():
            logging.info(f"Creating directory { self.path }")
            mkdir_p(self.path)

        # Process tree
        soup = BeautifulSoup(r.text, features="lxml")
        for link in soup.find_all("a"):
            # Skip ignores
            if link.text.startswith(".."):
                continue
            skip = False
            for ign in self.ignore:
                if ign in link.text.lower():
                    skip = True
                    break
            if skip:
                break

            obj = self.children.get(link.text)
            if obj is None:
                if link.text.endswith('/'):
                    obj = Dir(urljoin(self.url, link.get('href')),
                              self.path / link.text, self.ignore, session)
                else:
                    obj = File(urljoin(self.url, link.get('href')),
                               self.path / link.text, session)
                self.children[link.text] = obj

        for obj in self.children.values():
            obj.update()

        self.status = 'updated'

    def __repr__(self):
        return f'Dir({self.path}, {self.status})'



#%% On standalone execution
if __name__ == "__main__":
    descr = """
This script allows syncing a directory to another computer serving the files
through Python's simple HTTP server.

Comparison is done using only the file size.
"""

    epilog = """
Server side, in a Python-enabled prompt, cd to the wanted directory and run:

    $ python -m http.server [PORT] [--directory <DIRECTORY_TO_USE>]

*Note: The --directory option is available from Python 3.7 onwards and the
default port is 8000.

WARNING: remember that serving local files to external interfaces will put
those files in a security risk! Only do this if those files can be considered
public.
    """
    parser = argparse.ArgumentParser(description=descr, epilog=epilog,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('url', help="URL where the dir is served")
    parser.add_argument('-p', '--path', nargs="?", type=Path, default='.',
                        help="Directory to sync to. Default is the current"
                        'directory (".").')
    parser.add_argument('-l', '--loop', nargs="?", type=int, default=0,
                        help='If 0 (zero, default), syncs once and then quits.'
                        ' If greater than zero, waits this number of seconds '
                        'and then syncs again, in an infinite loop. Press '
                        'Ctrl+C or Ctrl+Break to quit.')

    parser.add_argument('-i', '--ignore', nargs="*", default=IGNORE,
                        help='Filenames to ignore when syncing (comparison is '
                        'case-insensitive. Default is to ignore these: ' +
                        f'{{ { ", ".join(IGNORE) } }}.')
    try:
        args = parser.parse_args()
    except:
        parser.print_help()
        raise

    FORMAT = '%(asctime)s %(levelname)-8s: %(message)s'
    logging.basicConfig(format=FORMAT, level=logging.INFO)
    # url = args.url; path = args.path; loop = args.loop; ignore = args.ignore
    sync(args.url, args.path, args.loop, args.ignore)
