#!/usr/bin/env python
# Python binding for Unicorn engine. Nguyen Anh Quynh <aquynh@gmail.com>

from __future__ import print_function
import glob
import os
import subprocess
import shutil
import sys
import platform

from distutils import log
from distutils.core import setup
from distutils.util import get_platform
from distutils.command.build import build
from distutils.command.sdist import sdist
from setuptools.command.bdist_egg import bdist_egg

SYSTEM = sys.platform
VERSION = '1.0.0'

# sys.maxint is 2**31 - 1 on both 32 and 64 bit mingw
IS_64BITS = platform.architecture()[0] == '64bit'

ALL_WINDOWS_DLLS = (
    "libwinpthread-1.dll",
    "libgcc_s_seh-1.dll" if IS_64BITS else "libgcc_s_dw2-1.dll",
    "libiconv-2.dll",
    "libpcre-1.dll",
    "libintl-8.dll",
)

# are we building from the repository or from a source distribution?
ROOT_DIR = os.path.dirname(os.path.realpath(__file__))
LIBS_DIR = os.path.join(ROOT_DIR, 'unicorn', 'lib')
HEADERS_DIR = os.path.join(ROOT_DIR, 'unicorn', 'include')
SRC_DIR = os.path.join(ROOT_DIR, 'src')
BUILD_DIR = SRC_DIR if os.path.exists(SRC_DIR) else os.path.join(ROOT_DIR, '../..')

if SYSTEM == 'darwin':
    LIBRARY_FILE = "libunicorn.dylib"
    STATIC_LIBRARY_FILE = 'libunicorn.a'
elif SYSTEM in ('win32', 'cygwin'):
    LIBRARY_FILE = "unicorn.dll"
    STATIC_LIBRARY_FILE = "unicorn.lib"
else:
    LIBRARY_FILE = "libunicorn.so"
    STATIC_LIBRARY_FILE = 'libunicorn.a'

def clean_bins():
    shutil.rmtree(LIBS_DIR, ignore_errors=True)
    shutil.rmtree(HEADERS_DIR, ignore_errors=True)

def copy_sources():
    """Copy the C sources into the source directory.
    This rearranges the source files under the python distribution
    directory.
    """
    src = []

    os.system('make -C %s clean' % os.path.join(ROOT_DIR, '../..'))
    shutil.rmtree(SRC_DIR, ignore_errors=True)
    os.mkdir(SRC_DIR)

    shutil.copytree(os.path.join(ROOT_DIR, '../../qemu'), os.path.join(SRC_DIR, 'qemu/'))
    shutil.copytree(os.path.join(ROOT_DIR, '../../include'), os.path.join(SRC_DIR, 'include/'))
    # make -> configure -> clean -> clean tests fails unless tests is present
    shutil.copytree(os.path.join(ROOT_DIR, '../../tests'), os.path.join(SRC_DIR, 'tests/'))
    # remove site-specific configuration file
    os.remove(os.path.join(SRC_DIR, 'qemu/config-host.mak'))

    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../*.[ch]")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../*.mk")))

    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../Makefile")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../LICENSE*")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../README.md")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../*.TXT")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../RELEASE_NOTES")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../make.sh")))
    src.extend(glob.glob(os.path.join(ROOT_DIR, "../../CMakeLists.txt")))

    for filename in src:
        outpath = os.path.join(SRC_DIR, os.path.basename(filename))
        log.info("%s -> %s" % (filename, outpath))
        shutil.copy(filename, outpath)

def build_libraries():
    """
    Prepare the unicorn directory for a binary distribution or installation.
    Builds shared libraries and copies header files.

    Will use a src/ dir if one exists in the current directory, otherwise assumes it's in the repo
    """
    cwd = os.getcwd()
    clean_bins()
    os.mkdir(HEADERS_DIR)
    os.mkdir(LIBS_DIR)

    # copy public headers
    shutil.copytree(os.path.join(BUILD_DIR, 'include', 'unicorn'), os.path.join(HEADERS_DIR, 'unicorn'))

    # copy special library dependencies
    if SYSTEM == 'win32':
        got_all = True
        for dll in ALL_WINDOWS_DLLS:
            dllpath = os.path.join(sys.prefix, 'bin', dll)
            dllpath2 = os.path.join(ROOT_DIR, 'prebuilt', dll)
            if os.path.exists(dllpath):
                shutil.copy(dllpath, LIBS_DIR)
            elif os.path.exists(dllpath2):
                shutil.copy(dllpath2, LIBS_DIR)
            else:
                got_all = False

        if not got_all:
            print('Warning: not all DLLs were found! This build is not appropriate for a binary distribution')
            # enforce this
            if 'upload' in sys.argv:
                sys.exit(1)

    # check if a prebuilt library exists
    # if so, use it instead of building
    if os.path.exists(os.path.join(ROOT_DIR, 'prebuilt', LIBRARY_FILE)):
        shutil.copy(os.path.join(ROOT_DIR, 'prebuilt', LIBRARY_FILE), LIBS_DIR)
        return

    # otherwise, build!!
    os.chdir(BUILD_DIR)

    # platform description refs at https://docs.python.org/2/library/sys.html#sys.platform
    new_env = dict(os.environ)
    new_env['UNICORN_BUILD_CORE_ONLY'] = 'yes'
    cmd = ['sh', './make.sh']
    if SYSTEM == "cygwin":
        if IS_64BITS:
            cmd.append('cygwin-mingw64')
        else:
            cmd.append('cygwin-mingw32')
    elif SYSTEM == "win32":
        if IS_64BITS:
            cmd.append('cross-win64')
        else:
            cmd.append('cross-win32')

    subprocess.call(cmd, env=new_env)

    shutil.copy(LIBRARY_FILE, LIBS_DIR)
    try:
        # static library may fail to build on windows if user doesn't have visual studio 12 installed. this is fine.
        shutil.copy(STATIC_LIBRARY_FILE, LIBS_DIR)
    except:
        pass
    os.chdir(cwd)


class custom_sdist(sdist):
    def run(self):
        clean_bins()
        copy_sources()
        return sdist.run(self)

class custom_build(build):
    def run(self):
        log.info("Building C extensions")
        build_libraries()
        return build.run(self)

class custom_bdist_egg(bdist_egg):
    def run(self):
        self.run_command('build')
        return bdist_egg.run(self)

def dummy_src():
    return []

cmdclass = {}
cmdclass['build'] = custom_build
cmdclass['sdist'] = custom_sdist
cmdclass['bdist_egg'] = custom_bdist_egg

if 'bdist_wheel' in sys.argv and '--plat-name' not in sys.argv:
    idx = sys.argv.index('bdist_wheel') + 1
    sys.argv.insert(idx, '--plat-name')
    name = get_platform()
    if 'linux' in name:
        # linux_* platform tags are disallowed because the python ecosystem is fubar
        # linux builds should be built in the centos 5 vm for maximum compatibility
        # see https://github.com/pypa/manylinux
        # see also https://github.com/angr/angr-dev/blob/master/bdist.sh
        sys.argv.insert(idx + 1, 'manylinux1_' + platform.machine())
    elif 'mingw' in name:
        if IS_64BITS:
            sys.argv.insert(idx + 1, 'win_amd64')
        else:
            sys.argv.insert(idx + 1, 'win32')
    else:
        # https://www.python.org/dev/peps/pep-0425/
        sys.argv.insert(idx + 1, name.replace('.', '_').replace('-', '_'))

try:
    from setuptools.command.develop import develop
    class custom_develop(develop):
        def run(self):
            log.info("Building C extensions")
            build_libraries()
            return develop.run(self)

    cmdclass['develop'] = custom_develop
except ImportError:
    print("Proper 'develop' support unavailable.")

def join_all(src, files):
    return tuple(os.path.join(src, f) for f in files)

setup(
    provides=['unicorn'],
    packages=['unicorn'],
    name='unicorn',
    version=VERSION,
    author='Nguyen Anh Quynh',
    author_email='aquynh@gmail.com',
    description='Unicorn CPU emulator engine',
    url='http://www.unicorn-engine.org',
    classifiers=[
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python :: 2',
        'Programming Language :: Python :: 3',
    ],
    requires=['ctypes'],
    cmdclass=cmdclass,
    zip_safe=True,
    include_package_data=True,
    is_pure=True,
    package_data={
        'unicorn': ['lib/*', 'include/unicorn/*']
    }
)
