# noqa: INP001
import os
import shutil
import subprocess
from sys import stdout

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        super().initialize(version, build_data)
        stdout.write(">>> Building Open Webui frontend\n")
        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "NodeJS `npm` is required for building Open Webui but it was not found"
            )
        stdout.write("### npm install\n")
        subprocess.run([npm, "install"], check=True)  # noqa: S603
        stdout.write("\n### npm run build\n")
        os.environ["APP_BUILD_HASH"] = version
        subprocess.run([npm, "run", "build"], check=True)  # noqa: S603
