#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Optimize the operation for Huawei and other mobile for myself based.
Original author is 冰蓝

TODO:
 - Handle the different photos with the same file name in the copy.
  - Rename some files to the new name
  - Need database to trace the change
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

# Default image folder
DEFAULT_PHOTO_DIR = '../imgs'
DEFAULT_TARGET_DIR = os.path.join('..', 'photos-by-date')


# Only process images, videos
ALLOWED_EXTENSIONS = ('.jpg', '.jpeg', '.gif','.png','.mp4')
IGNORE_FOLDERS = ('.thumbs', 'Quik/.thumbnails', 'Camera/cache/latest')

# Filename date gussing settings
SPLITERS = ['_', ' ', '-']
DATE_FORMATS = ['%Y%m%d', '%Y_%m_%d', '%Y-%m-%d']


HELP_TEXT = """Backup mobile photos according to the date to target directory

This tools is to back up the mobile photo and video files to the target directory and keep the original files without change. The sub folders will be created in the target directory, which will be named by the year and months of file.

Usage:
    %s <arguments>

Arguments:
    -s --source=source directory of photos, default '%s'.
    -t --target=target directory to back up files, default '%s'.
    -h --help       This help page
"""  % (os.path.split(__file__)[-1], DEFAULT_PHOTO_DIR, DEFAULT_TARGET_DIR)

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
                except ValueError, err:
                    pass

def getExifDate(filename):
    try:
        fd = open(filename, 'rb')
    except:
        print("Not able to open file[%s]\n" % filename)
        return
    data = exifread.process_file( fd )
    if data:
        try:
            return datetime.strptime(str(data['EXIF DateTimeOriginal'])[:10], '%Y:%m:%d')
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
        #print("Exif date is", date)
        return date

    date = guessDateByFileName(filename)
    #print("File date is befoe filenaem", date)
    if date != None:
        #print("File name '%s' date is %s" % (filename,date))
        return date

    date = getFileModifiedDate(filename)
    if date != None:
        #print("File modifiled date is", date)
        return date

    print( "Error: no date information. Take 2000-01-01 for %s" % filename)
    return datetime(2000, 1,1)

def copyPhotoToFolder(filename, fileFullPath, source, target):
    """Copy the file to the target folder with year/month sub folder
    Return 1 if the copy a new file to the target folder.
    """
    name, extension = os.path.splitext(filename)
    if extension.lower() not in ALLOWED_EXTENSIONS:
        print("Skip '%s': file type is not supported. " % filename)
        return 0

    for folder in IGNORE_FOLDERS:
        if fileFullPath.find(folder) > 0:
            print("Skip: %s folder is set to ignore" % folder)
            return 0

    date = getFileDate(fileFullPath)

    targetDir = os.path.join(target, "%04d" % date.year)
    if not os.path.exists(targetDir):
        os.mkdir(targetDir)
    targetDir = os.path.join(targetDir, "%02d" % date.month)
    if not os.path.exists(targetDir):
        os.mkdir(targetDir)

    targetFilePath = os.path.join(targetDir, filename)

    # Copy the file to the target directory
    if not os.path.exists(targetFilePath):
        shutil.copy2( fileFullPath, targetFilePath )
        print "[%s] %s" % (date.strftime("%Y-%m-%d"), fileFullPath)
        return 1
    else:
        # Skip the existing file with the same file name.
        # TODO: Make the file comparasion and consider the strategy to handle same name files
        # print "Skip '%s': already exists." % fileFullPath
        return 0

def classifyPhoto(source, target):
    if not os.path.exists(source):
        print("The source path '%s' does not exist")
        return

    if not os.path.exists(target ):
        os.mkdir(target)

    newPhotos = 0

    for root,dirs,files in os.walk(source, True):
        for filename in files:
            fileFullPath = os.path.join(root, filename)
            newPhotos += copyPhotoToFolder(filename, fileFullPath, source, target)

    print("Copy %d new photos or videos to the '%s'." % (newPhotos, target))


if __name__ == "__main__":
    source = DEFAULT_PHOTO_DIR
    target = DEFAULT_TARGET_DIR

    try:
        opts,args=getopt.getopt(sys.argv[1:],"s:t:h",["source=","target=","help"])
        for option, arg in opts:
            if option in ['--source', '-s']:
                source = arg
            if option in ['--target', '-t']:
                target = arg
            if option in ['--help', '-h']:
                print HELP_TEXT
                sys.exit()
    except getopt.GetoptError as err:
        print err
        sys.exit()

    classifyPhoto(source, target)
