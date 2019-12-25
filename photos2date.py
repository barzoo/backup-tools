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

###############################################################################
# Default image folder
DEFAULT_PHOTO_DIR = 'imgs'
DEFAULT_TARGET_DIR = 'photos-by-date'
DEFAULT_LOG_FILE = 'picture-by-date.log'

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
    {thisScript} <arguments>

Arguments:
    -s --source=source directory of photos, default '{DEFAULT_PHOTO_DIR}'.
    -t --target=target directory to back up, default '{DEFAULT_TARGET_DIR}'.
    -l --log-file=log file, default '{DEFAULT_LOG_FILE}'.
    -h --help       This help page.
""".format(thisScript=os.path.split(__file__)[-1],
           DEFAULT_PHOTO_DIR=DEFAULT_PHOTO_DIR,
           DEFAULT_TARGET_DIR=DEFAULT_TARGET_DIR,
           DEFAULT_LOG_FILE=DEFAULT_LOG_FILE)
###############################################################################


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
    '''Read EXIF data information from the picture file
    '''
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
    '''Get the date by the file modification time.
    '''
    fstat = os.stat(filename)
    return datetime.fromtimestamp(fstat[stat.ST_MTIME])


def getFileDate(filename):
    """Define the strategy of looking the date of the file
    """
    date = getExifDate(filename)
    if date != None:
        logging.debug("Exif date is {date}".format(date=date))
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

        logging.debug("New name: {next_name} - [{increase}]".format(
            next_name=next_name, increase=increase))

        targetPath = next_name + extension

        if os.path.exists(targetPath):
            if not filecmp.cmp(targetPath, fileFullPath):
                increase += 1
            else:
                logging.info("Existed \"{targetPath}\", give up.".format(
                    targetPath=targetPath))
                break
        else:
            shutil.copy2(fileFullPath, targetPath)
            return 1
    logging.info("Failed on \"{targetPath}\" after {increase} times".format(
        targetPath=targetPath, increase=increase))
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
    logReplace = "Add to [{picDateStr}]: \"{fileFullPath}\".".format(
        picDateStr=picDateStr, fileFullPath=fileFullPath
    )
    # Copy the file to the target directory
    if not os.path.exists(targetFilePath):
        shutil.copy2(fileFullPath, targetFilePath)
        logging.info(logReplace)
        return 1
    elif not filecmp.cmp(targetFilePath, fileFullPath):
        # Make the file comparasion and handle same name files
        logging.info("Duplicated name \"{targetFilePath}\". ".format(
            targetFilePath=targetFilePath))
        count = copyDuplicatedFile(targetFilePath, fileFullPath)
        if count > 0:
            logging.info(logReplace)
            return count
    # Skip the existing file with the same file name.
    logging.debug("Skip [{picDateStr}]: \"{fileFullPath}\" ".format(
        picDateStr=picDateStr,
        fileFullPath=fileFullPath) + " already existed as"
        " \"{targetFilePath}\".".format(targetFilePath=targetFilePath))
    return 0


def classifyPhoto(source, target):
    '''Scan the pictures from the source directory and copy to the target
    directory with the date formated folders.

    :param source: source directory contains pictures
    :param target: target directory to save the pictures
    '''
    if not os.path.exists(source):
        logging.error("The source path '{source}' does not exist".format(
            source=source))
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

    logging.info("Copy {newPhotos} new picture to the '{target}'.".format(
        newPhotos=newPhotos, target=target))


if __name__ == "__main__":
    source = DEFAULT_PHOTO_DIR
    target = DEFAULT_TARGET_DIR
    logFile = DEFAULT_LOG_FILE

    try:
        opts, args = getopt.getopt(sys.argv[1:], "s:t:l:h", [
                                   "source=", "target=", "log-file" "help"])
        for option, arg in opts:
            if option in ['--source', '-s']:
                source = arg
            if option in ['--target', '-t']:
                target = arg
            if option in ['--log-file', '-l']:
                logFile = arg

            if option in ['--help', '-h']:
                print(HELP_TEXT)
                sys.exit()
    except getopt.GetoptError as err:
        print(err)
        sys.exit()

    # Create the target folder before logging
    if not os.path.exists(target):
        os.mkdir(target)

    # Configure the logging file
    logging.basicConfig(level=logging.INFO,
                        format='[%(asctime)s %(levelname)s] %(message)s',
                        datefmt='%d %b %Y %H:%M:%S',
                        filename=os.path.join(target, logFile)
                        )

    console = logging.StreamHandler()
    console.setLevel(logging.INFO)
    logging.getLogger('').addHandler(console)

    classifyPhoto(source, target)
