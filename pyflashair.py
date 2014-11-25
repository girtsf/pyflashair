#!/usr/bin/python
#
# Simple library to fetch/sync files from a Toshiba FlashAir SD card.
#
# Specification: https://flashair-developers.com/en/documents/api/commandcgi/

from __future__ import print_function, unicode_literals, division

import argparse
import collections
import datetime
import os
import sys
import urllib2

# Timeout in seconds for each operation.
DEFAULT_TIMEOUT = 5

OP_GET_FILE_LIST = 100

# A structure describing a single file.
File = collections.namedtuple('File', 'dir name size attr datetime')

# A structure describing file/dir attributes. Each item is a boolean.
Attributes = collections.namedtuple(
    'Attributes', 'archive dir volume system hidden ro')


class FlashAir(object):
  """Class that talks to a FlashAir SD card."""

  def __init__(self, address, timeout=DEFAULT_TIMEOUT):
    self._address = address
    self._timeout = timeout

  def _BuildOpUrl(self, op, extra_args=None):
    """Builds a URL for a command.cgi operation."""
    url = 'http://%s/command.cgi?op=%d' % (self._address, op)
    if extra_args:
      url += '&' + extra_args
    return url

  def _BuildFileUrl(self, path):
    """Builds a URL for downloading a file."""
    return 'http://%s/%s' % (self._address, path)

  def _GetOp(self, op, extra_args=None):
    """Executes given operation, returns stripped lines as a list."""
    url = self._BuildOpUrl(op, extra_args=extra_args)
    fh = urllib2.urlopen(url, timeout=self._timeout)
    result = [x.strip() for x in fh.readlines()]
    fh.close()
    return result

  def _GetFile(self, path):
    """Fetches a given file."""
    url = self._BuildFileUrl(path)
    fh = urllib2.urlopen(url, timeout=self._timeout)
    result = fh.read()
    fh.close()
    return result

  @staticmethod
  def _DecodeAttributes(attr):
    """Decodes file list entry attributes."""
    return Attributes(
        archive=bool(attr & (1 << 5)),
        dir=bool(attr & (1 << 4)),
        volume=bool(attr & (1 << 3)),
        system=bool(attr & (1 << 2)),
        hidden=bool(attr & (1 << 1)),
        ro=bool(attr & (1 << 0)),
    )

  @staticmethod
  def _DecodeDateAndTime(d, t):
    """Decodes a date and time value."""
    year = ((d >> 9) & 0b1111111) + 1980
    month = (d >> 5) & 0b1111
    day = d & 0b11111
    hour = (t >> 11) & 0b11111
    minute = (t >> 5) & 0b111111
    second = (t & 0b11111) * 2
    return datetime.datetime(year, month, day, hour, minute, second)

  def GetFileList(self, directory):
    """Given a remote directory, returns a list of File structs."""
    lines = self._GetOp(OP_GET_FILE_LIST, 'DIR=%s' % directory)
    assert lines[0] == 'WLANSD_FILELIST'
    results = []
    for line in lines[1:]:
      items = line.rsplit(',', 6)
      results.append(File(
        dir=items[0],
        name=items[1],
        size=int(items[2]),
        attr=self._DecodeAttributes(int(items[3])),
        datetime=self._DecodeDateAndTime(int(items[4]), int(items[5]))))
    return results

  def RecursiveFileList(self, directory, levels=0):
    """Prints out file names recursively scanning all directories."""
    for f in self.GetFileList(directory):
      s = ' ' * (levels * 2)
      s += f.name
      if f.attr.dir:
        s += '/'
      else:
        s += ' | %d bytes' % f.size
      s += ' | %s' % f.datetime
      print(s)
      if f.attr.dir:
        self.RecursiveFileList(directory + '/' + f.name, levels=(levels+1))

  def Sync(self, remote_dir, local_dir, force_lowercase=True):
    """Syncs remote dir to local dir."""
    print('Syncing %s -> %s' % (remote_dir, local_dir))
    if not os.path.exists(local_dir):
      raise ValueError('%s does not exist' % local_dir)
    files = self.GetFileList(remote_dir)
    for f in files:
      print(f.name)
      fetch = False
      remote_file = os.path.join(remote_dir, f.name)
      local_file = os.path.join(local_dir, f.name)
      if force_lowercase:
        local_file = local_file.lower()
      if f.attr.dir:
        if not os.path.exists(local_file):
          os.mkdir(local_file)
        else:
          assert os.path.isdir(local_file)
        self.Sync(remote_file, local_file, force_lowercase=force_lowercase)
      else:
        if not os.path.exists(local_file):
          print('  does not exist locally, fetching...')
          fetch = True
        elif os.stat(local_file).st_size != f.size:
          print('  size differs, fetching...')
          fetch = True
        if fetch:
          contents = self._GetFile(remote_file)
          with open(local_file, 'wb') as fh:
            fh.write(contents)


def Main():
  parser = argparse.ArgumentParser(
      description='Utility to talk to an AirFlash SD card.')
  parser.add_argument(
      '--address',
      help='Device hostname or IP address.',
      required=True)
  group = parser.add_mutually_exclusive_group(required=True)
  group.add_argument(
      '--sync',
      help='Synchronizes a remote directory to a local directory.',
      nargs=2,
      metavar=('<remote-dir>', '<local-dir>'))
  group.add_argument(
      '--ls',
      help='Lists remote directory contents recursivively.',
      nargs='?',
      const='/',
      metavar='<remote-dir>')

  args = parser.parse_args()
  flashair = FlashAir(args.address)
  if args.ls:
    flashair.RecursiveFileList(args.ls)
  elif args.sync:
    flashair.Sync(args.sync[0], args.sync[1])
  else:
    parser.print_help()


if __name__ == '__main__':
  Main()
