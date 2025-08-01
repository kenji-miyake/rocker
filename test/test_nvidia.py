# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.

import docker
import em
import unittest
import pexpect
import pytest


from io import BytesIO as StringIO
from packaging.version import Version

from rocker.core import DockerImageGenerator
from rocker.core import list_plugins
from rocker.core import get_docker_client
from rocker.nvidia_extension import get_docker_version
from test_extension import plugin_load_parser_correctly


@pytest.mark.docker
class X11Test(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        client = get_docker_client()
        self.dockerfile_tags = []
        for distro, distro_version in [('ubuntu', 'jammy'), ('ubuntu', 'noble'), ('debian', 'bookworm')]:
            dockerfile = """
FROM %(distro)s:%(distro_version)s

RUN apt-get update && apt-get install x11-utils -y && apt-get clean

CMD xdpyinfo
"""
            dockerfile_tag = 'testfixture_%s_x11_validate' % distro_version
            iof = StringIO((dockerfile % locals()).encode())
            im = client.build(fileobj = iof, tag=dockerfile_tag)
            for e in im:
                pass
                #print(e)
            self.dockerfile_tags.append(dockerfile_tag)

    def setUp(self):
        # Work around interference between empy Interpreter
        # stdout proxy and test runner. empy installs a proxy on stdout
        # to be able to capture the information.
        # And the test runner creates a new stdout object for each test.
        # This breaks empy as it assumes that the proxy has persistent
        # between instances of the Interpreter class
        # empy will error with the exception
        # "em.Error: interpreter stdout proxy lost"
        em.Interpreter._wasProxyInstalled = False

    def test_x11_extension_basic(self):
        plugins = list_plugins()
        x11_plugin = plugins['x11']
        self.assertEqual(x11_plugin.get_name(), 'x11')
        self.assertTrue(plugin_load_parser_correctly(x11_plugin))
        
        p = x11_plugin()
        mock_cliargs = {'base_image': 'ubuntu:xenial'}

        # Must be called before get_docker_args
        docker_args = p.precondition_environment(mock_cliargs)

        docker_args = p.get_docker_args(mock_cliargs)
        self.assertIn(' -e DISPLAY -e TERM', docker_args)
        self.assertIn(' -e QT_X11_NO_MITSHM=1', docker_args)
        self.assertIn(' -e XAUTHORITY=', docker_args)
        self.assertIn(' -v /tmp/.X11-unix:/tmp/.X11-unix ', docker_args)
        self.assertIn(' -v /etc/localtime:/etc/localtime:ro ', docker_args)

    def test_x11_extension_nocleanup(self):
        plugins = list_plugins()
        x11_plugin = plugins['x11']        
        p = x11_plugin()
        mock_cliargs = {'base_image': 'ubuntu:xenial', 'nocleanup': True}
        docker_args = p.precondition_environment(mock_cliargs)
        # TODO(tfoote) do more to check that it doesn't actually clean up.
        # This is more of a smoke test


    def test_no_x11_xpdyinfo(self):
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator([], {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertNotEqual(dig.run(), 0)

    @pytest.mark.x11
    def test_x11_xpdyinfo(self):
        plugins = list_plugins()
        desired_plugins = ['x11']
        active_extensions = [e() for e in plugins.values() if e.get_name() in desired_plugins]
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator(active_extensions, {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertEqual(dig.run(), 0)


@pytest.mark.docker
class NvidiaTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        client = get_docker_client()
        self.dockerfile_tags = []
        for distro_version in ['xenial', 'bionic']:
            dockerfile = """
FROM ubuntu:%(distro_version)s

RUN apt-get update && apt-get install glmark2 -y && apt-get clean

CMD glmark2 --validate
"""
            dockerfile_tag = 'testfixture_%s_glmark2' % distro_version
            iof = StringIO((dockerfile % locals()).encode())
            im = client.build(fileobj = iof, tag=dockerfile_tag)
            for e in im:
                pass
                #print(e)
            self.dockerfile_tags.append(dockerfile_tag)

    def setUp(self):
        # Work around interference between empy Interpreter
        # stdout proxy and test runner. empy installs a proxy on stdout
        # to be able to capture the information.
        # And the test runner creates a new stdout object for each test.
        # This breaks empy as it assumes that the proxy has persistent
        # between instances of the Interpreter class
        # empy will error with the exception
        # "em.Error: interpreter stdout proxy lost"
        em.Interpreter._wasProxyInstalled = False

    def test_nvidia_extension_basic(self):
        plugins = list_plugins()
        nvidia_plugin = plugins['nvidia']
        self.assertEqual(nvidia_plugin.get_name(), 'nvidia')
        self.assertTrue(plugin_load_parser_correctly(nvidia_plugin))
        
        p = nvidia_plugin()
        mock_cliargs = {'base_image': 'ubuntu:xenial'}
        snippet = p.get_snippet(mock_cliargs)

        self.assertIn('COPY --from=glvnd /usr/local/lib/x86_64-linux-gnu /usr/local/lib/x86_64-linux-gnu', snippet)
        self.assertIn('COPY --from=glvnd /usr/local/lib/i386-linux-gnu /usr/local/lib/i386-linux-gnu', snippet)
        self.assertIn('ENV LD_LIBRARY_PATH /usr/local/lib/x86_64-linux-gnu:/usr/local/lib/i386-linux-gnu', snippet)
        self.assertIn('NVIDIA_VISIBLE_DEVICES', snippet)
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES', snippet)

        mock_cliargs = {'base_image': 'ubuntu:bionic'}
        snippet = p.get_snippet(mock_cliargs)
        self.assertIn('RUN apt-get update && apt-get install -y --no-install-recommends', snippet)
        self.assertIn(' libglvnd0 ', snippet)
        self.assertIn(' libgles2 ', snippet)
        self.assertIn('COPY --from=glvnd /usr/share/glvnd/egl_vendor.d/10_nvidia.json /usr/share/glvnd/egl_vendor.d/10_nvidia.json', snippet)

        self.assertIn('NVIDIA_VISIBLE_DEVICES', snippet)
        self.assertIn('NVIDIA_DRIVER_CAPABILITIES', snippet)


        preamble = p.get_preamble(mock_cliargs)
        self.assertIn('FROM nvidia/opengl:1.0-glvnd-devel-ubuntu18.04', preamble)

        mock_cliargs = {'base_image': 'ubuntu:jammy'}
        preamble = p.get_preamble(mock_cliargs)
        self.assertIn('FROM nvidia/opengl:1.0-glvnd-devel-ubuntu22.04', preamble)

        mock_cliargs = {'base_image': 'ubuntu:jammy', 'nvidia_glvnd_version': '20.04'}
        preamble = p.get_preamble(mock_cliargs)
        self.assertIn('FROM nvidia/opengl:1.0-glvnd-devel-ubuntu20.04', preamble)

        docker_args = p.get_docker_args(mock_cliargs)
        #TODO(tfoote) restore with #37 self.assertIn(' -e DISPLAY -e TERM', docker_args)
        #TODO(tfoote) restore with #37 self.assertIn(' -e QT_X11_NO_MITSHM=1', docker_args)
        #TODO(tfoote) restore with #37 self.assertIn(' -e XAUTHORITY=', docker_args)
        #TODO(tfoote) restore with #37 self.assertIn(' -v /tmp/.X11-unix:/tmp/.X11-unix ', docker_args)
        #TODO(tfoote) restore with #37 self.assertIn(' -v /etc/localtime:/etc/localtime:ro ', docker_args)
        if get_docker_version() >= Version("19.03"):
            self.assertIn(' --gpus all', docker_args)
        else:
            self.assertIn(' --runtime=nvidia', docker_args)

        mock_cliargs = {'nvidia': 'auto'}
        docker_args = p.get_docker_args(mock_cliargs)
        if get_docker_version() >= Version("19.03"):
            self.assertIn(' --gpus all', docker_args)
        else:
            self.assertIn(' --runtime=nvidia', docker_args)

        mock_cliargs = {'nvidia': 'gpus'}
        docker_args = p.get_docker_args(mock_cliargs)
        self.assertIn(' --gpus all', docker_args)

        mock_cliargs = {'nvidia': 'runtime'}
        docker_args = p.get_docker_args(mock_cliargs)
        self.assertIn(' --runtime=nvidia', docker_args)


    def test_no_nvidia_glmark2(self):
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator([], {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertNotEqual(dig.run(), 0)

    @pytest.mark.nvidia
    @pytest.mark.x11
    def test_nvidia_glmark2(self):
        plugins = list_plugins()
        desired_plugins = ['x11', 'nvidia', 'user'] #TODO(Tfoote) encode the x11 dependency into the plugin and remove from test here
        active_extensions = [e() for e in plugins.values() if e.get_name() in desired_plugins]
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator(active_extensions, {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertEqual(dig.run(), 0)

    def test_nvidia_env_subs(self):
        plugins = list_plugins()
        nvidia_plugin = plugins['nvidia']

        p = nvidia_plugin()

        # base image doesn't exist
        mock_cliargs = {'base_image': 'ros:does-not-exist'}
        with self.assertRaises(SystemExit) as cm:
            p.get_environment_subs(mock_cliargs)
        self.assertEqual(cm.exception.code, 1)

        # unsupported version
        mock_cliargs = {'base_image': 'ubuntu:17.04'}
        with self.assertRaises(SystemExit) as cm:
            p.get_environment_subs(mock_cliargs)
        self.assertEqual(cm.exception.code, 1)

        # unsupported os
        mock_cliargs = {'base_image': 'fedora'}
        with self.assertRaises(SystemExit) as cm:
            p.get_environment_subs(mock_cliargs)
        self.assertEqual(cm.exception.code, 1)

@pytest.mark.docker
@pytest.mark.nvidia # Technically not needing nvidia but too resource intensive for main runs
class CudaTest(unittest.TestCase):
    @classmethod
    def setUpClass(self):
        client = get_docker_client()
        self.dockerfile_tags = []
        for (distro_name, distro_version) in [
            ('ubuntu','focal'),
            ('ubuntu','jammy'),
            ('ubuntu','noble'),
            ('debian','bookworm'),
            ('debian','bullseye'),
            ]:
            dockerfile = """
FROM %(distro_name)s:%(distro_version)s
CMD dpkg -s cuda-toolkit
"""
            dockerfile_tag = 'testfixture_%s_cuda' % distro_version
            iof = StringIO((dockerfile % locals()).encode())
            im = client.build(fileobj = iof, tag=dockerfile_tag)
            for e in im:
                pass
                #print(e)
            self.dockerfile_tags.append(dockerfile_tag)

    def setUp(self):
        # Work around interference between empy Interpreter
        # stdout proxy and test runner. empy installs a proxy on stdout
        # to be able to capture the information.
        # And the test runner creates a new stdout object for each test.
        # This breaks empy as it assumes that the proxy has persistent
        # between instances of the Interpreter class
        # empy will error with the exception
        # "em.Error: interpreter stdout proxy lost"
        em.Interpreter._wasProxyInstalled = False


    def test_no_cuda(self):
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator([], {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertNotEqual(dig.run(), 0)
            dig.clear_image()

    def test_cuda_install(self):
        plugins = list_plugins()
        desired_plugins = ['cuda']
        active_extensions = [e() for e in plugins.values() if e.get_name() in desired_plugins]
        for tag in self.dockerfile_tags:
            dig = DockerImageGenerator(active_extensions, {}, tag)
            self.assertEqual(dig.build(), 0)
            self.assertEqual(dig.run(), 0)
            dig.clear_image()

    def test_cuda_env_subs(self):
        plugins = list_plugins()
        cuda_plugin = plugins['cuda']

        p = cuda_plugin()

        # base image doesn't exist
        mock_cliargs = {'base_image': 'ros:does-not-exist'}
        with self.assertRaises(SystemExit) as cm:
            p.get_environment_subs(mock_cliargs)
        self.assertEqual(cm.exception.code, 1)

        # unsupported version
        mock_cliargs = {'base_image': 'ubuntu:17.04'}
        with self.assertRaises(SystemExit) as cm:
            p.get_environment_subs(mock_cliargs)
        self.assertEqual(cm.exception.code, 1)

        # unsupported os
        mock_cliargs = {'base_image': 'fedora'}
        with self.assertRaises(SystemExit) as cm:
            p.get_environment_subs(mock_cliargs)
        self.assertEqual(cm.exception.code, 1)
