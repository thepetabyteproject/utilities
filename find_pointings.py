#!/usr/bin/env python3
#
# Script for grabbing pointing coordinates and related information for The Petabyte Project.
# Created 04/01/22 by Graham Doskoch. Last modified 05/22/23.
#
# This script searches through data files in a directory and its subdirectories
# and grabs relevant information about each pointing, currently including MJD,
# right ascension, declination and central frequency. The input is a tab-separated
# text file listing each top-level directory to search, listed by the survey it
# belongs to. The output is a tab-separated text file containg the information
# requested, as well as several lists of paths that caused errors during the search,
# including broken symlinks, empty files and files that are strangely encoded.
# It currently searches .fits and .fil files. It isn't fast, but ideally we won't
# have to run this more than a couple of times.
#
# The script is run by
# >> python find_pointings.py input_file output_file_prefix
#
# An example input file can be found at /home/gd00010/TPP/PALFA/PALFA_dir_list.txt.
# The resulting output, PALFA_output_list.txt, can be found in the same directory.

import argparse
import os
import subprocess
import sys

parser = argparse.ArgumentParser(description='Grab information about pointings')
parser.add_argument('i', type=str, help='Input file of directories to search')
parser.add_argument('o', type=str, help='Prefix of output file to write to')
parser.add_argument('--b', type=str, help='File containing list of data files to ignore')
args = parser.parse_args()

prop_names = ['Path', 'Survey', 'Telescope', 'Frontend', 'Backend', 'MJD',
    'RA J2000', 'Dec J2000', 'Freq', 'Length', 'Sampling time', 'Bandwidth',
    'Freq channels', 'Num_pols', 'Source name', 'Bits', 'Beam', 'f_high', 'f_low',
    'Pol_type', 'Backend_mode']

print('Reading directory list from {}.'.format(args.i))
dir_list = [line.strip().split('\t') for line in open(args.i, 'r').readlines()]
dir_list = sorted(dir_list)

ignored_files = []
ignored_dirs = []

# Some files cause issues, known or unknown. This bit ensures that those
# files will be ignored by the rest of the script.
if args.b:
    ignored = open(args.b, 'r').readlines()
    ignored = [f.replace('\n', '').split('\t') for f in ignored]
    print('Reading directories and files to ignore from {}.'.format(args.b))
    for f in ignored:
        if f[0] == 'file':
            ignored_files.append(f[1])
        elif f[0] == 'directory':
            ignored_dirs.append(f[1])

def parse_fits_or_fil(path):
    """Takes in the path to a .fits/.fil file and returns the desired pointing
    information by calling readfile and psredit, since not quite all of the
    properties of interesting can be found with readfile. Going forward I could
    shift to a psredit-only workflow.
    """

    props = {} # dictionary of the various file properties/parameters

    # If any of the fields is not listed in the header, the value will be listed
    # as "None" in the point list, giving us an easy way to search for files missing
    # important information.
    for name in prop_names:
        props[name] = 'None'
    filename = os.path.basename(path)
    temp_filename = '{}.txt'.format(os.path.splitext(filename)[0])
    #os.system('readfile {} >> {}'.format(path, temp_filename))
    try:
        proc = subprocess.check_call('readfile {} >> {}'.format(path, temp_filename), shell=True)
    except subprocess.CalledProcessError:
        #proc = subprocess.Popen('readfile {} >> {}'.format(path, temp_filename), shell=True)
        print('Y', path)
        sys.exit()
    # I *should* use subprocess.Popen(), but that seems to break things. C'est la vie.

    file = open(temp_filename, 'r')
    file = file.readlines()

    props['Beam'] = 0 # default if there are no beams
    for line in file:
        line = line.strip()
        line = line.split(' = ')
        try:
            if line[0] in prop_names:
                props[line[0]] = line[1]
            if 'MJD start time' in line[0]:
                props['MJD'] = line[1]
            if line[0] == 'Central freq (MHz)':
                props['Freq'] = line[1]
            if line[0] == 'Source Name':
                props['Source name'] = line[1]
            if line[0] == 'Sample time (us)':
                props['Sampling time'] = str(float(line[1])/(10**3))
            if 'Total Bandwidth' in line[0]:
                props['Bandwidth'] = line[1]
            if line[0] == 'Number of channels':
                props['Freq channels'] = line[1]
            if line[0] == 'Polarization type':
                props['Pol_type'] = line[1]
            if line[0] == 'Number of polns':
                props['Num_pols'] = line[1].split(' ')[0]
            if 'bits' in line[0]:
                props['Bits'] = line[1]
            if line[0] == 'Beam':
                props['Beam'] = line[1].split(' of ')[0]
            if line[0] == 'Low channel (MHz)':
                props['f_high'] = line[1]
            if line[0] == 'High channel (MHz)':
                props['f_low'] = line[1]
            if 'Time per file' in line[0]:
                props['Length'] = line[1]
        except IndexError:
            pass
    os.remove(temp_filename)

    if os.path.splitext(path)[1] != '.fil':
        # .fil files can't be read with psredit; I need a workaround
        proc = subprocess.check_call('psredit {} >> {}'.format(path, temp_filename), shell=True)
        file = open(temp_filename, 'r')
        file = file.readlines()

        for line in file:
            line = line.strip()
            while '\t' in line:
                line = line.replace('\t', ' ')
            while '  ' in line:
                line = line.replace('  ', ' ')
            if 'obs_mode' in line:
                props['Backend_mode'] = line.split()[-1]

        os.remove(temp_filename)

    if 'None' in props.values():
        bad_props = []
        for name in prop_names:
            if prop_names[name] == 'None':
                bad_props.append(name)
        message = 'Warning: {} fields have no values listed:'.format(len(bad_props))
        for name in bad_props:
            message += ' {},'.format(name)
        message = message[:-1]
        print(message)

    return props

def check_file_size(path):
    """Takes in a file and checks whether that file has non-zero size"""

    process = subprocess.Popen('ls -l {}'.format(path), stdout=subprocess.PIPE, shell=True)
    output, error = process.communicate()
    inf = output.decode('UTF-8')
    size = int(inf.split(' ')[4])
    return size

def is_good(path):
    """Checks that a file is not in the list of blacklisted/ignore files"""

    good = True
    for d in ignored_dirs:
        if d in path:
            good = False
    if path in ignored_files:
        good = False
    return good

def grab_pointings_from_survey(survey, loc):
    """Takes in a survey name and the location of its directory and grabs
    information about each pointing within the directory. This is the main
    portion of this script."""

    pointings = []

    # There are three major failure modes: a file actually being a symlink that
    # is broken, a file being empty, or a file being improperly encoded. The
    # script does not process those files (it can't!), but it does create
    # separate lists of them, for convenience.
    broken_symlinks = []
    empty_files = []
    encoding_errors = []

    for root, dirs, files in os.walk(loc):
        for filename in files:
            for ext in ['.fits', '.fil']:
                path = os.path.join(root, filename)
                if filename.endswith(ext) and 'cal' not in filename and is_good(path) == True:
                    print('Searching {}.'.format(path))
                    # Note that this function returns the full path to the file,
                    # not just the filename!

                    if os.path.islink(path):
                        if os.path.exists(os.readlink(path)):
                            exists = True
                        else:
                            print('{} appears to be a broken symlink and will not be read.'.format(path))
                            broken_symlinks.append(path)
                            exists = False
                    else:
                        exists = True
                    # The above deals with the case where a symlink is broken - in
                    # which case it will still be listed in the directory but may
                    # cause readfile to crash. If that's the case, the script should
                    # skip over the symlink.

                    if exists == True and check_file_size(path) != 0:
                        try:
                            props = parse_fits_or_fil(path)
                            props['Path'] = path
                            props['Survey'] = survey
                            info = [props[name] for name in prop_names]
                            pointings.append(info)
                        except UnicodeDecodeError:
                            os.remove('{}.txt'.format(os.path.splitext(filename)[0]))
                            print('{} caused readfile to incorrectly encode and will not be read'.format(path))
                            encoding_errors.append(path)
                    elif check_file_size(path) == 0:
                        print('{} has size zero and will not be read.'.format(path))
                        empty_files.append(path)
                elif is_good(path) == False:
                    print('{} has been blacklisted and will not be read.'.format(path))

    return pointings, broken_symlinks, empty_files, encoding_errors

pointings = []
broken_symlinks = []
empty_files = []
encoding_errors = []
for entry in dir_list:
    survey, path = entry
    print('Searching for pointings from {} in {}.'.format(survey, path))
    survey_pointings, survey_broken_symlinks, survey_empty_files, survey_encoding_errors = grab_pointings_from_survey(survey, path)
    print('{} {} pointings found!'.format(len(survey_pointings), survey))
    pointings += survey_pointings
    broken_symlinks += survey_broken_symlinks
    empty_files += survey_empty_files
    encoding_errors += survey_encoding_errors
print('{} total pointings found!'.format(len(pointings)))

output_file = open('{}_output_list.txt'.format(args.o), 'w')
print('Writing pointings to {}_output_list.txt.'.format(args.o))
for pointing in pointings:
    pointing = '\t'.join(pointing)
    pointing += '\n'
    output_file.write(pointing)
output_file.close()

def write_errors_to_file(list_of_paths, term):
    """Writes problematic paths to their respective files"""

    if len(list_of_paths) > 0:
        error_file = open('{}_{}.txt'.format(args.o, '_'.join(term.split(' '))), 'w')
        print('Writing {} to {}_{}.txt'.format(term, args.o, '_'.join(term.split(' '))))
        for path in list_of_paths:
            path += '\n'
            error_file.write(path)
        error_file.close()
    else:
        print('No {} found.'.format(term))

write_errors_to_file(broken_symlinks, 'broken symlinks')
write_errors_to_file(empty_files, 'empty files')
write_errors_to_file(encoding_errors, 'encoding errors')
