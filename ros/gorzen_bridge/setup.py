from setuptools import find_packages, setup

package_name = "gorzen_bridge"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        ("share/ament_index/resource_index/packages", ["resource/" + package_name]),
        ("share/" + package_name, ["package.xml"]),
        ("share/" + package_name + "/config", ["config/bridge_params.yaml"]),
    ],
    install_requires=["setuptools", "httpx"],
    zip_safe=True,
    maintainer="Gorzen Dev",
    maintainer_email="dev@gorzen.io",
    description="ROS 2 bridge between PX4 uXRCE-DDS topics and Gorzen planner REST API",
    license="MIT",
    entry_points={
        "console_scripts": [
            "bridge_node = gorzen_bridge.bridge_node:main",
        ],
    },
)
