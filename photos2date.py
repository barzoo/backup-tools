#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Optimize the operation for Huawei and other mobile for myself based.
Original author is 冰蓝

TODO:
 - Handle the different photos with the same file name in the copy.
  - Rename some files to the new name (Done)
  - Need database to trace the change (Add logging)
 - inotify support to watch the source directory
   avoid too much actions for most existing files
 - Copy photo and video files to different folders
"""

import shutil
import os
import stat
import getopt
import sys
import exifread
from datetime import datetime
import filecmp
import re
import logging

# Configure the logging into a file to tracing.
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s %(levelname)s] %(message)s',
                    datefmt='%d %b %Y %H:%M:%S',
                    filename='picture-by-date.log'
                    )

console = logging.StreamHandler()
console.setLevel(logging.INFO)
logging.getLogger('').addHandler(console)

# Default image folder
DEFAULT_PHOTO_DIR = 'imgs'
DEFAULT_TARGET_DIR = 'photos-by-date'


# Only process images, videos
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.gif', '.png', '.mp4')
IGNORE_FOLDERS = ('.thumbs', 'Quik/.thumbnails', 'Camera/cache/latest')

# Filename date gussing settings
SPLITERS = ['_', ' ', '-']
DATE_FORMATS = ['%Y%m%d', '%Y_%m_%d', '%Y-%m-%d']


HELP_TEXT = """Backup mobile photos according to the date to target directory

This tools is to back up the mobile photo and video files to the target
directory and keep the original files without change. The sub folders will be
created in the target directory, which will be named by the year and months of
file.

Usage:
    %s <arguments>

Arguments:
    -s --source=source directory of photos, default '%s'.
    -t --target=target directory to back up files, default '%s'.
    -h --help       This help page
""" % (os.path.split(__file__)[-1], DEFAULT_PHOTO_DIR, DEFAULT_TARGET_DIR)


def guessDateByFileName(filename):
    """
    Guess the date by the filename
    Examples of the filename with the date
    VID_20190909_090909.mp4  with spliter '-' and format '%Y%m%d'
    20160111_154215_yunle.mp4
    20151214_084655_001.mp4
    20150515_195309.mp4
    """
    pureFileName = os.path.split(filename)[-1]
    for spliter in SPLITERS:
        for datefmt in DATE_FORMATS:
            for segment in pureFileName.split(spliter):
                try:
                    date = datetime.strptime(segment, datefmt)
                    return date
                except ValueError as err:
                    pass


def getExifDate(filename):
    try:
        fd = open(filename, 'rb')
    except:
        logging.error("Not able to open file[%s]\n" % filename)
        return
    data = exifread.process_file(fd)
    if data:
        try:
            return datetime.strptime(
                str(data['EXIF DateTimeOriginal'])[:10], '%Y:%m:%d')
        except:
            pass


def getFileModifiedDate(filename):
    fstat = os.stat(filename)
    return datetime.fromtimestamp(fstat[stat.ST_MTIME])


def getFileDate(filename):
    """Define the strategy of looking the date of the file
    """
    date = getExifDate(filename)
    if date != None:
        logging.debug(f"Exif date is {date}")
        return date

    date = guessDateByFileName(filename)
    logging.debug("File date is befoe filenaem", date)
    if date != None:
        logging.debug("File name '%s' date is %s" % (filename, date))
        return date

    date = getFileModifiedDate(filename)
    if date != None:
        logging.debug("File modifiled date is", date)
        return date

    logging.error(
        "Error: no date information. Take 2000-01-01 for %s" % filename)
    return datetime(2000, 1, 1)


def copyDuplicatedFile(targetFilePath, fileFullPath):
    """Rename the duplicated file with additional postfix and copy
    """
    MAX_TRIES = 10
    REG_POSTFIX = r'-p(\d+)$'
    EX_POSTFIX = '-p'

    increase = 1
    targetPath = targetFilePath

    while increase < MAX_TRIES:
        name, extension = os.path.splitext(targetPath)
        results = re.search(REG_POSTFIX, name)

        if results:
            next_name = int(results.group(1)) + increase
            next_name = re.sub(REG_POSTFIX, EX_POSTFIX + str(next_name), name)
        else:
            next_name = name + EX_POSTFIX + '1'

        logging.debug(f"New name: {next_name} - [{increase}]")

        targetPath = next_name + extension

        if os.path.exists(targetPath):
            if not filecmp.cmp(targetPath, fileFullPath):
                increase += 1
            else:
                logging.debug(f"Duplicated \"{targetPath}\", give up.")
                break
        else:
            shutil.copy2(fileFullPath, targetPath)
            return 1
    logging.info(f"Give up duplicated \"{targetPath}\" after {increase} times")
    return 0


def copyPhotoToFolder(filename, fileFullPath, source, target):
    """Copy the file to the target folder with year/month sub folder
    Return 1 if the copy a new file to the target folder.
    """
    name, extension = os.path.splitext(filename)
    if extension.lower() not in ALLOWED_EXTENSIONS:
        logging.info("Skip '%s': file type is not supported. " % filename)
        return 0

    for folder in IGNORE_FOLDERS:
        if fileFullPath.find(folder) > 0:
            logging.info("Skip: %s folder is set to ignore" % folder)
            return 0

    picDate = getFileDate(fileFullPath)

    targetDir = os.path.join(target, "%04d" % picDate.year)
    if not os.path.exists(targetDir):
        os.mkdir(targetDir)
    targetDir = os.path.join(targetDir, "%02d" % picDate.month)
    if not os.path.exists(targetDir):
        os.mkdir(targetDir)

    targetFilePath = os.path.join(targetDir, filename)
    picDateStr = picDate.strftime("%Y-%m-%d")
    logReplace = f"Add to [{picDateStr}]: \"{fileFullPath}\"."
    # Copy the file to the target directory
    if not os.path.exists(targetFilePath):
        shutil.copy2(fileFullPath, targetFilePath)
        logging.info(logReplace)
        return 1
    elif not filecmp.cmp(targetFilePath, fileFullPath):
        # Make the file comparasion and handle same name files
        logging.info(f"Duplicated \"{targetFilePath}\" with different content")
        count = copyDuplicatedFile(targetFilePath, fileFullPath)
        if count > 0:
            logging.info(logReplace)
            return count
    # Skip the existing file with the same file name.
    logging.debug(f"Skip [{picDateStr}]: \"{fileFullPath}\" already existed as"
                  f" \"{targetFilePath}\".")
    return 0


def classifyPhoto(source, target):
    if not os.path.exists(source):
        logging.error(f"The source path '{source}' does not exist")
        return

    if not os.path.exists(target):
        os.mkdir(target)

    newPhotos = 0

    for root, dirs, files in os.walk(source, True):
        for filename in files:
            fileFullPath = os.path.join(root, filename)
            newPhotos += copyPhotoToFolder(filename,
                                           fileFullPath,
                                           source,
                                           target)

    logging.info(f"Copy {newPhotos} new photos or videos to the '{target}'.")


if __name__ == "__main__":
    source = DEFAULT_PHOTO_DIR
    target = DEFAULT_TARGET_DIR

    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:t:h", [
                                   "source=", "target=", "help"])
        for option, arg in opts:
            if option in ['--source', '-s']:
                source = arg
            if option in ['--target', '-t']:
                target = arg
            if option in ['--help', '-h']:
                print(HELP_TEXT)
                sys.exit()
    except getopt.GetoptError as err:
        logging.error(err)
        sys.exit()

    classifyPhoto(source, target)
