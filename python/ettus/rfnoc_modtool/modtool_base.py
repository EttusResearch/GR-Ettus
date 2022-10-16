#
# Copyright 2013 Free Software Foundation, Inc.
#
# This file is part of GNU Radio
#
# GNU Radio is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3, or (at your option)
# any later version.
#
# GNU Radio is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with GNU Radio; see the file COPYING.  If not, write to
# the Free Software Foundation, Inc., 51 Franklin Street,
# Boston, MA 02110-1301, USA.
#
""" Base class for the modules """

from __future__ import print_function
from __future__ import absolute_import
import os
import re
from argparse import ArgumentParser
from gnuradio import gr
from .util_functions import get_modname
from .scm import SCMRepoFactory

class ModToolException(BaseException):
    """ Standard exception for modtool classes. """
    pass

class ModTool(object):
    """ Base class for all modtool command classes. """
    # pylint: disable=too-many-instance-attributes
    name = 'base'
    def __init__(self):
        #List subdirs where stuff happens
        self._subdirs = ['lib', 'include', 'python', 'swig', 'grc', 'examples', 'rfnoc']
        self._has_subdirs = {}
        self._skip_subdirs = {}
        self._info = {}
        self._file = {}
        for subdir in self._subdirs:
            self._has_subdirs[subdir] = False
            self._skip_subdirs[subdir] = False
        self.parser = self.setup_parser()
        self._dir = None

    def setup_parser(self):
        """ Init the option parser. If derived classes need to add options,
        override this and call the parent function. """
        parser = ArgumentParser(
            usage='%(prog)s ' + self.name + ' [options] <PATTERN> \n' + \
            ' Call "%(prog)s ' + self.name + '" without any options to run it' + \
            ' interactively.',
            add_help=False
            )
        agroup = parser.add_argument_group("General options")
        agroup.add_argument("-h", "--help",
                            action="help",
                            help="Displays this help message.")
        agroup.add_argument("-d", "--directory",
                            default=".",
                            help="Base directory of the module. Defaults to the cwd.")
        agroup.add_argument("-n", "--module-name",
                            default=None,
                            help="Use this to override the current module's name" + \
                                    " (is normally autodetected).")
        agroup.add_argument("-N", "--block-name",
                            default=None,
                            help="Name of the block, where applicable.")
        agroup.add_argument("--skip-lib",
                            action="store_true",
                            default=False,
                            help="Don't do anything in the lib/ subdirectory.")
        agroup.add_argument("--skip-swig",
                            action="store_true",
                            default=False,
                            help="Don't do anything in the swig/ subdirectory.")
        agroup.add_argument("--skip-python",
                            action="store_true",
                            default=False,
                            help="Don't do anything in the python/ subdirectory.")
        agroup.add_argument("--skip-grc",
                            action="store_true",
                            default=False,
                            help="Don't do anything in the grc/ subdirectory.")
        agroup.add_argument("--skip-examples",
                            action="store_true",
                            default=False,
                            help="Don't do anything in the examples/ subdirectory.")
        agroup.add_argument("--skip-rfnoc",
                            action="store_true",
                            default=False,
                            help="Don't do anything in the rfnoc/ subdirectory.")
        agroup.add_argument("--scm-mode",
                            choices=('yes', 'no', 'auto'),
                            default=gr.prefs().get_string('rfnocmodtool', 'scm_mode', 'no'),
                            help="Use source control management (yes, no or auto).")
        agroup.add_argument("-y", "--yes",
                            action="store_true",
                            default=False,
                            help="Answer all questions with 'yes'. This " + \
                                 "can overwrite and delete your files, so be careful.")
        return parser

    def setup(self, args, positional):
        """ Initialise all internal variables, such as the module name etc. """
        self._dir = args.directory
        self._info['modpath'] = os.path.abspath(self._dir)
        if not self._check_directory(self._dir):
            raise ModToolException('No RFNoC module found in the given directory.')
        if args.module_name is not None:
            self._info['modname'] = args.module_name
        else:
            self._info['modname'] = get_modname()
        if self._info['modname'] is None:
            raise ModToolException('No RFNoC module found in the given directory.')
        print("RFNoC module name identified: " + self._info['modname'])
        if self._info['version'] == '36' and (
                os.path.isdir(os.path.join('include', self._info['modname'])) or
                os.path.isdir(os.path.join('include', 'gnuradio', self._info['modname']))):
            self._info['version'] = '37'
        if args.skip_lib or not self._has_subdirs['lib']:
            self._skip_subdirs['lib'] = True
        if args.skip_python or not self._has_subdirs['python']:
            self._skip_subdirs['python'] = True
        if args.skip_swig or self._get_mainswigfile() is None or not self._has_subdirs['swig']:
            self._skip_subdirs['swig'] = True
        if args.skip_grc or not self._has_subdirs['grc']:
            self._skip_subdirs['grc'] = True
        if args.skip_grc or not self._has_subdirs['examples']:
            self._skip_subdirs['examples'] = True
        if args.skip_grc or not self._has_subdirs['grc']:
            self._skip_subdirs['rfnoc'] = True
        self._info['blockname'] = args.block_name
        self._setup_files()
        self._info['yes'] = args.yes
        self.args = args
        self._setup_scm()

    def _setup_files(self):
        """ Initialise the self._file[] dictionary """
        if not self._skip_subdirs['swig']:
            self._file['swig'] = os.path.join('swig', self._get_mainswigfile())
        self._info['pydir'] = 'python'
        if os.path.isdir(os.path.join('python', self._info['modname'])):
            self._info['pydir'] = os.path.join('python', self._info['modname'])
        self._file['qalib'] = os.path.join('lib', 'qa_%s.cc' % self._info['modname'])
        self._file['pyinit'] = os.path.join(self._info['pydir'], '__init__.py')
        self._file['cmlib'] = os.path.join('lib', 'CMakeLists.txt')
        self._file['cmgrc'] = os.path.join('grc', 'CMakeLists.txt')
        self._file['cmpython'] = os.path.join(self._info['pydir'], 'CMakeLists.txt')
        if self._info['is_component']:
            self._info['includedir'] = os.path.join('include', 'gnuradio', self._info['modname'])
        elif self._info['version'] == '37':
            self._info['includedir'] = os.path.join('include', self._info['modname'])
        else:
            self._info['includedir'] = 'include'
        self._file['cminclude'] = os.path.join(self._info['includedir'], 'CMakeLists.txt')
        self._file['cmswig'] = os.path.join('swig', 'CMakeLists.txt')
        self._file['cmfind'] = os.path.join('cmake', 'Modules', 'rfnoc_exampleConfig.cmake')

    def _setup_scm(self, mode='active'):
        """Initialize source control management. """
        if mode == 'active':
            self.scm = SCMRepoFactory(self.args, '.').make_active_scm_manager()
        else:
            self.scm = SCMRepoFactory(self.args, '.').make_empty_scm_manager()
        if self.scm is None:
            print("Error: can't set up SCM")
            exit(1)

    def _check_directory(self, directory):
        """ Guesses if dir is a valid RFNoC module directory by looking for
        CMakeLists.txt and at least one of the subdirs lib/, python/ and swig/.
        Changes the directory, if valid. """
        has_makefile = False
        try:
            files = os.listdir(directory)
            os.chdir(directory)
        except OSError:
            print("Can't read or chdir to directory %s." % directory)
            return False
        self._info['is_component'] = False
        for f in files:
            if os.path.isfile(f) and f == 'CMakeLists.txt':
                if re.search(r'find_package\(Gnuradio', open(f).read()) is not None:
                    self._info['version'] = '36' # Might be 37, check that later
                    has_makefile = True
                elif re.search('GR_REGISTER_COMPONENT', open(f).read()) is not None:
                    self._info['version'] = '36' # Might be 37, check that later
                    self._info['is_component'] = True
                    has_makefile = True
            # TODO search for autofoo
            elif os.path.isdir(f):
                if f in self._has_subdirs.keys():
                    self._has_subdirs[f] = True
                else:
                    self._skip_subdirs[f] = True
        return bool(has_makefile and (self._has_subdirs.values()))

    def _get_mainswigfile(self):
        """ Find out which name the main SWIG file has. In particular, is it
            a MODNAME.i or a MODNAME_swig.i? Returns None if none is found. """
        modname = self._info['modname']
        swig_files = (modname + '.i',
                      modname + '_swig.i')
        for fname in swig_files:
            if os.path.isfile(os.path.join(self._dir, 'swig', fname)):
                return fname
        return None

    def run(self):
        """ Override this. """
        pass

def get_class_dict(the_globals):
    " Return a dictionary of the available commands in the form command->class "
    classdict = {}
    for glob in the_globals:
        try:
            if issubclass(glob, ModTool):
                classdict[glob.name] = glob
                for alias in glob.aliases:
                    classdict[alias] = glob
        except (TypeError, AttributeError):
            pass
    return classdict
