from setuptools import find_packages, setup
from glob import glob
import os

package_name = "conveyor_decision_manager"

setup(
    name=package_name,
    version="0.0.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        (os.path.join("share", package_name, "launch"), glob("launch/*.launch.py")),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="jetsonherbie",
    maintainer_email="jetsonherbie@example.com",
    description="Decision manager for conveyor command priority",
    license="Apache-2.0",
    tests_require=["pytest"],
    entry_points={
        "console_scripts": [
            "decision_manager_node = conveyor_decision_manager.decision_manager_node:main",
        ],
    },
)
