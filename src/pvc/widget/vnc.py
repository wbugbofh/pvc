"""
VNC module

"""

import os
import random
import socket
import string
import time
import tempfile

import pyVmomi

from subprocess import Popen, PIPE

from pvc.widget.form import Form, FormElement
from pvc.widget.menu import Menu, MenuItem
from pvc.widget.gauge import TaskGauge

__all__ = ['VncWidget']


class VncWidget(object):
    def __init__(self, dialog, obj):
        """
        VNC widget

        Args:
            dialog      (dialog.Dialog): A Dialog instance
            obj    (vim.VirtualMachine): A vim.VirtualMachine managed entity

        """
        if not isinstance(obj, pyVmomi.vim.VirtualMachine):
            raise TypeError('Need a vim.VirtualMachine instance')

        self.dialog = dialog
        self.obj = obj
        self.display()

    def _port_is_opened(self, host, port):
        """
        Probes a port to check if it is opened or not

        Returns:
            True if the port is opened, False otherwise

        """
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        err_code = sock.connect_ex((host, port))
        sock.close()

        return not err_code

    def _get_available_port(self, attempts):
        """
        Look for available port to use for the VNC console

        We search for available port on the HostSystem where
        our Virtual Machine is running in the port range 5901-5999.

        Args:
            attempts (int): Perform that many iterations when searching for a port

        Returns:
            A random port in the range 5901-5999 if an available
            port was found, None otherwise

        """
        self.dialog.infobox(
            title=self.obj.name,
            text='Searching for available port ...'
        )

        host = self.obj.runtime.host
        host_ip = host.config.network.vnic[0].spec.ip.ipAddress

        for i in range(attempts):
            random_port = 5900 + random.randrange(1, 99)
            if not self._port_is_opened(host=host_ip, port=random_port):
                return random_port

        return None

    def _get_random_password(self, length=8):
        """
        Get a random password

        Args:
            length (int): Length of the returned password

        """
        chars = string.ascii_letters + string.digits

        return ''.join(random.choice(chars) for _ in range(length))

    def _get_extra_config_options(self):
        """
        Get Virtual Machine extra configuration options

        Returns:
            A dictionary of the extra config options

        """
        return {o.key:o.value for o in self.obj.config.extraConfig}

    def _configure_vnc_options(self, enabled, port, password):
        """
        Configure VNC console options

        Args:
            enabled (bool): If True enable the VNC console
            port     (int): VNC port to be configured
            password (str): VNC password to be configured

        """
        options = [
            pyVmomi.vim.OptionValue(key='RemoteDisplay.vnc.enabled', value=str(enabled)),
            pyVmomi.vim.OptionValue(key='RemoteDisplay.vnc.port', value=str(port)),
            pyVmomi.vim.OptionValue(key='RemoteDisplay.vnc.password', value=str(password)),
        ]
        spec = pyVmomi.vim.VirtualMachineConfigSpec(extraConfig=options)

        task = self.obj.Reconfigure(spec=spec)
        gauge = TaskGauge(
            title=self.obj.name,
            text='Configuring VNC Settings',
            dialog=self.dialog,
            task=task
        )
        gauge.display()

    def display(self):
        """
        Main widget method

        """
        items = [
            MenuItem(
                tag='Console',
                description='Launch VNC Console',
                on_select=self.launch_console
            ),
            MenuItem(
                tag='Enable',
                description='Enable VNC Console',
                on_select=self.enable_vnc
            ),
            MenuItem(
                tag='Disable',
                description='Disable VNC Console',
                on_select=self.disable_vnc
            ),
            MenuItem(
                tag='Settings',
                description='Manual VNC Configuration',
                on_select=self.settings
            ),
        ]

        menu = Menu(
            title=self.obj.name,
            items=items,
            dialog=self.dialog
        )

        menu.display()

    def enable_vnc(self):
        """
        Enable VNC Console for the Virtual Machine

        """
        self.dialog.infobox('Enabling VNC Console ...')

        extra_config = self._get_extra_config_options()
        enabled = extra_config.get('RemoteDisplay.vnc.enabled')
        port = extra_config.get('RemoteDisplay.vnc.port')
        password = extra_config.get('RemoteDisplay.vnc.password')

        if str(enabled).lower() == 'true':
            self.dialog.msgbox(
                title=self.obj.name,
                text='VNC console is already enabled'
            )
            return

        port = port if port else self._get_available_port(attempts=10)
        if not port:
            self.dialog.msgbox(
                title=self.obj.name,
                text='No available ports for VNC connection, try again later.'
            )
            return

        password = password if password else self._get_random_password()
        self._configure_vnc_options(
            enabled=True,
            port=port,
            password=password
        )

    def disable_vnc(self):
        """
        Disable VNC console for the Virtual Machine

        """
        options = [
            pyVmomi.vim.OptionValue(key='RemoteDisplay.vnc.enabled', value='false'),
        ]
        spec = pyVmomi.vim.VirtualMachineConfigSpec(extraConfig=options)

        task = self.obj.Reconfigure(spec=spec)
        gauge = TaskGauge(
            title=self.obj.name,
            text='Disabling VNC Console',
            dialog=self.dialog,
            task=task
        )
        gauge.display()

    def settings(self):
        """
        Manual configuration of the VNC settings

        """
        extra_config = self._get_extra_config_options()
        enabled = extra_config.get('RemoteDisplay.vnc.enabled', 'false')
        port = extra_config.get('RemoteDisplay.vnc.port', '')
        password = extra_config.get('RemoteDisplay.vnc.password', '')

        elements = [
            FormElement(
                label='Enabled',
                item=enabled
            ),
            FormElement(
                label='Port',
                item=port
            ),
            FormElement(
                label='Password',
                item=password,
                input_length=8
            )
        ]

        form = Form(
            dialog=self.dialog,
            form_elements=elements,
            title=self.obj.name,
            text='VNC Configuration Options'
        )

        code, fields = form.display()
        if not all(fields.values()):
            self.dialog.msgbox(
                title=self.obj.name,
                text='Invalid configuration settings'
            )
            return

        if code == self.dialog.OK:
            self._configure_vnc_options(
                enabled=fields['Enabled'],
                port=fields['Port'],
                password=fields['Password']
            )

    def launch_console(self):
        """
        Launch a VNC Console

        """
        if self.obj.runtime.powerState != pyVmomi.vim.VirtualMachinePowerState.poweredOn:
            self.dialog.msgbox(
                title=self.obj.name,
                text='You need to power on the Virtual Machine first'
            )
            return

        extra_config = self._get_extra_config_options()
        enabled = extra_config.get('RemoteDisplay.vnc.enabled')
        port = extra_config.get('RemoteDisplay.vnc.port')
        password = extra_config.get('RemoteDisplay.vnc.password')

        if str(enabled).lower() != 'true':
            self.dialog.msgbox(
                title=self.obj.name,
                text='VNC console is disabled, enable the console first'
            )
            return

        host = self.obj.runtime.host
        host_ip = host.config.network.vnic[0].spec.ip.ipAddress

        if not self._port_is_opened(host=host_ip, port=int(port)):
            text = (
                'Host {} with IP address {} is not reachable on port {}\n'
                'Cannot establish a connection to the Virtual Machine console\n'
            )
            self.dialog.msgbox(
                title=self.obj.name,
                text=text.format(host, host_ip, port)
            )
            return

        try:
            fd, vncpasswd_file = tempfile.mkstemp(prefix='pvcvnc_')
            with Popen(args=['vncpasswd', '-f'], stdin=PIPE, stdout=PIPE, stderr=PIPE) as p:
                data = '{0}\n{0}\n'.format(password)
                out, err = p.communicate(bytes(data, 'utf-8'))
            with open(vncpasswd_file, 'wb') as f:
                f.write(out)
        except OSError as e:
            self.dialog.msgbox(
                title=self.obj.name,
                text='Cannot create a vncpasswd(1) file: \n{}\n'.format(e)
            )
            return

        self.dialog.infobox(
            text='Launching console ...'
        )

        try:
            Popen(
                args=['vncviewer', '-passwd', vncpasswd_file, '{}:{}'.format(host_ip, port)],
                stdout=PIPE,
                stderr=PIPE
            )
        except OSError as e:
            self.dialog.msgbox(
                title=self.obj.name,
                text='Cannot start vncviewer(1): \n{}\n'.format(e)
            )

        time.sleep(3)
        os.unlink(vncpasswd_file)
