#!/usr/bin/env python

import json
import os
import shutil
import sys
import gpxpy, gpxpy.gpx

from argparse import ArgumentParser, ArgumentTypeError
from contextlib import contextmanager
from glob import glob
from subprocess import Popen, PIPE


@contextmanager
def chdir(dirname=None):
    curdir = os.getcwd()
    os.chdir(dirname)
    try:
        yield
    finally:
        os.chdir(curdir)


def gpxfile(string):
    """ Validates string is an existing gpx file for argument parser"""

    if not os.path.isfile(string) or os.path.splitext(string)[1] != '.gpx':
        raise ArgumentTypeError("'%s' is not a gpx file" % string)
    return string


def directory(string):
    """ Validates string is an existing directory for argument parser"""

    if not os.path.isdir(string):
        raise ArgumentTypeError("'%s' is not an existing directory" % string)
    return string


def geotag(scriptdir, gpxfilepath, inputdir, outputdir, workdir='.'):
    basename = os.path.splitext(os.path.basename(gpxfilepath))[0]

    print 'Geotagging images'
    # keeps command open in a thread
    cmd = ['exiftool', '-geotag', gpxfilepath, '-geotime<FileModifyDate',
           '-P', '-o', workdir, '-stay_open', 'true', '-@', '-']
    proc = Popen(cmd, stdin=PIPE)
    # pipe matched images to command
    images = glob(os.path.join(inputdir, 'G[!O]*.JPG'))
    args = '\n'.join(images + ['-execute', '-stay_open', 'false'])
    proc.communicate(args + '\n')
    print 'Success'

    print 'Extracting geotags from images'
    tmpjsonfile = open('tmp.json', 'w+')
    cmd = ['exiftool', '-config', os.path.join(scriptdir, 'ExifTool_config'),
           '-GPSLatitude', '-GPSLongitude', '-json', workdir]
    proc = Popen(cmd, stdout=tmpjsonfile)
    proc.communicate()
    tmpjsonfile.close()
    # parse json and delete images that didn't get geotagged
    tmpjsonfile = open('tmp.json', 'r')
    waypoints = json.load(tmpjsonfile)
    missing_waypoints = []
    for waypoint in waypoints:
        if not 'GPSLatitude' in waypoint:
            missing_waypoints.append(waypoint)
    for waypoint in missing_waypoints:
        os.remove(waypoint['SourceFile'])
        waypoints.remove(waypoint)
    print 'Success'

    print 'Adding image geotags to gpx as waypoints'
    # parse gpx file
    gpxfile = open(os.path.abspath(gpxfilepath), 'r+')
    gpx = gpxpy.parse(gpxfile)
    gpxfile.close()
    # add waypoints
    for waypoint in waypoints:
        lat, lon = (float(waypoint['GPSLatitude']), float(waypoint['GPSLongitude']))
        gpx.waypoints.append(gpxpy.gpx.GPXWaypoint(lat, lon))
    # combine track segments into one
    for track in gpx.tracks:
        while len(track.segments) > 1:
            track.join(0)
    # write result
    tmpgpxfile = open('tmp.gpx', 'w+')
    tmpgpxfile.write(gpx.to_xml())
    tmpgpxfile.close()
    # create geojson from new gpx
    jsonfile = open('.'.join((basename, 'json')), 'w+')
    cmd = ['togeojson', os.path.abspath('tmp.gpx')]
    proc = Popen(cmd, stdout=jsonfile)
    proc.communicate()
    # trim whitespace
    jsonfile.seek(0)
    lines = jsonfile.readlines()
    clean_lines = [l.strip() for l in lines if l.strip()]
    jsonfile.seek(0)
    jsonfile.writelines(''.join(clean_lines))
    jsonfile.truncate()
    jsonfile.close()
    print 'Success'

    print 'Cleaning up temp files'
    os.remove('tmp.gpx')
    os.remove('tmp.json')
    print 'Success'

    print 'Creating mp4'
    cmd = ['ffmpeg', '-r', '5', '-pattern_type', 'glob', '-i',
           os.path.join(workdir, 'G*.JPG'), '-c:v', 'libx264', '-pix_fmt',
           'yuv420p', '-s', '920x690', '-preset', 'veryslow', '-tune',
           'stillimage', '-profile:v', 'baseline', '-level', '3.0',
           '-movflags', '+faststart', '.'.join((basename, 'mp4'))]
    proc = Popen(cmd)
    proc.communicate()
    print 'Success'

    print 'Creating webm'
    cmd = ['ffmpeg', '-r', '5', '-pattern_type', 'glob', '-i',
           os.path.join(workdir, 'G*.JPG'), '-c:v', 'libvpx', '-crf', '10',
           '-b:v', '4M', '-c:a', 'libvorbis', '-s', '920x690',
           '.'.join((basename, 'webm'))]
    proc = Popen(cmd)
    proc.communicate()
    print 'Success'

    print 'Moving images to destination'
    for filename in glob('G*.JPG'):
        try:
            # shutil won't remove originals in linux when copying to another filesystem.
            # oh well. wrap it and get over it.
            shutil.move(filename, outputdir)
        except Exception, e:
            pass
    print 'Success'

    return 1


def argument_parser():
    """Creates the object that parses arguments from the command-line interface"""

    parser = ArgumentParser(description="Geotags images from a gpx file, adds \
                                         those tags back to the gpx file as \
                                         waypoints, then moves the edited \
                                         images to a destination.")
    parser.add_argument('gpxfilepath', metavar='GPXFILE', type=gpxfile, nargs='?',
                        help="Path to the gpx file to get geotagging data from.")
    parser.add_argument('inputdir', metavar='INPUTDIR', type=directory, nargs='?',
                        help="Path to the directory containing the unedited \
                              photos.")
    parser.add_argument('outputdir', metavar='OUTPUTDIR', type=directory, nargs='?',
                        help="Path to where the edited images will be saved.")
    parser.add_argument('workdir', type=directory, nargs='?', default='.',
                        help="Path to the directory where editing is done. \
                              Defaults to current directory.")
    return parser

if __name__ == '__main__':
    args = argument_parser().parse_args()

    scriptdir = os.path.dirname(os.path.realpath(sys.argv[0]))

    with chdir(args.workdir):
        sys.exit(geotag(scriptdir, **vars(args)))
