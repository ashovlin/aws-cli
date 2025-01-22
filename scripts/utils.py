import contextlib
import json
import os
import platform
import shutil
import sys
import subprocess
import tempfile
import zipfile
import glob

class BadRCError(Exception):
    pass


def run(cmd, cwd=None, env=None, echo=True):
    if echo:
        sys.stdout.write("Running cmd: %s\n" % cmd)
    kwargs = {
        'shell': True,
        'stdout': subprocess.PIPE,
        'stderr': subprocess.PIPE,
    }
    if isinstance(cmd, list):
        kwargs['shell'] = False
    if cwd is not None:
        kwargs['cwd'] = cwd
    if env is not None:
        kwargs['env'] = env
    p = subprocess.Popen(cmd, **kwargs)
    stdout, stderr = p.communicate()
    output = stdout.decode('utf-8') + stderr.decode('utf-8')
    if p.returncode != 0:
        raise BadRCError("Bad rc (%s) for cmd '%s': %s" % (
            p.returncode, cmd, output))
    return output


def extract_zip(zipfile_name, target_dir):
        with zipfile.ZipFile(zipfile_name, 'r') as zf:
            for zf_info in zf.infolist():
                # Check if it's a symlink
                is_symlink = (zf_info.external_attr & 0xF0000000) == 0xA0000000

                if is_symlink:
                    # Read the symlink target
                    target_path = zf.read(zf_info.filename).decode()
                    # Construct the full path for the symlink
                    symlink_path = os.path.join(target_dir, zf_info.filename)
                    # Create the parent directory if it doesn't exist
                    os.makedirs(os.path.dirname(symlink_path), exist_ok=True)
                    os.symlink(target_path, symlink_path)
                else:
                    # Handle regular files as before
                    extracted_path = zf.extract(zf_info, target_dir)
                    os.chmod(extracted_path, zf_info.external_attr >> 16)


@contextlib.contextmanager
def tmp_dir():
    dirname = tempfile.mkdtemp()
    try:
        yield dirname
    finally:
        shutil.rmtree(dirname)


@contextlib.contextmanager
def cd(dirname):
    original = os.getcwd()
    os.chdir(dirname)
    try:
        yield
    finally:
        os.chdir(original)


def bin_path():
    """Get the system's binary path, either `bin` on reasonable systems
    or `Scripts` on Windows.
    """
    path = "bin"

    if platform.system() == "Windows":
        path = "Scripts"

    return path


def virtualenv_enabled():
    # Helper function to see if we need to make
    # our own virtualenv for installs.
    return bool(os.environ.get('VIRTUAL_ENV'))


def update_metadata(dirname, **kwargs):
    print('Update metadata values %s' % kwargs)
    metadata_file = os.path.join(dirname, 'awscli', 'data', 'metadata.json')
    with open(metadata_file) as f:
        metadata = json.load(f)
    for key, value in kwargs.items():
        metadata[key] = value
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f)


def remove_dist_info(dirname):
    with cd(dirname):
        for distinfo in glob.glob("**/*.dist-info", recursive=True):
            path = os.path.join(dirname, distinfo)
            shutil.rmtree(path)


def save_to_zip(dirname, zipfile_name):
    if zipfile_name.endswith('.zip'):
        zipfile_name = zipfile_name[:-4]
    shutil.make_archive(zipfile_name, 'zip', dirname)


def zip_preserve_symlinks(source_path, zip_path):
    print(fr'Zipping {source_path} to {zip_path}')
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(source_path):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, source_path)
                if os.path.islink(full_path):
                    # Store symlink information
                    zinfo = zipfile.ZipInfo.from_file(full_path, rel_path)
                    zinfo.external_attr = 0xA1ED0000  # symlink attribute
                    zf.writestr(zinfo, os.readlink(full_path))
                else:
                    zf.write(full_path, rel_path)
