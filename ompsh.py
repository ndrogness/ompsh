
import sys
import os
import micropython
import gc

HAVE_NET = True

if sys.implementation.name == 'micropython':
    import binascii as ompsh_binascii
    import network as ompsh_network
    import socket as ompsh_socket

elif sys.implementation.name == 'circuitpython':
    try:
        import adafruit_binascii as ompsh_binascii
    except ImportError:
        print('adafruit-circuitpython-binascii is required when using circuitpython, please install')
        sys.exit(-1)
    except RuntimeError:
        print('Error importing adafruit-circuitpython-binascii')
        sys.exit(-1)

    try:
        import network as ompsh_network
        import socket as ompsh_socket
    except ImportError:
        print('network stack not available')
        HAVE_NET = False


__version__ = "0.0.0"
__repo__ = "https://github.com/ndrogness/ompsh"


def net_ioctl(net_info):
    """
    A Network Interface
    :param net_info: dict of networkinfo
    :return:  True if connected, False otherwise
    """

    # net_info = {
    #     'connected': False -l
    #     'linkstatus': 'DOWN',
    #     'mode': 1,
    #     'interface': 'STA_IF',
    #     'mac': 'XX:XX;XX:XX;XX;XX',
    #     'wifimode': 'STA',
    #     'ip': '0.0.0.0',
    #     'netmask': '0.0.0.0',
    #     'dns1': '0.0.0.0',
    #     'dns2': '0.0.0.0'
    # }

    if HAVE_NET is True:
        sta_if = ompsh_network.WLAN(ompsh_network.STA_IF)
        if net_info is None:
            return sta_if.isconnected()
        else:
            net_info['active'] = False
            net_info['connected'] = False
            net_info['linkstatus'] = 'DOWN'
            net_info['mode'] = 1
            net_info['interface'] = 'STA_IF'
            net_info['mac'] = 'XX:XX:XX:XX:XX:XX'
            net_info['wifimode'] = 'STA'
            net_info['ip'] = '0.0.0.0'
            net_info['netmask'] = '0.0.0.0'
            net_info['dns1'] = '0.0.0.0'
            net_info['dns2'] = '0.0.0.0'

    else:
        return False

    net_info['active'] = sta_if.active()

    # AbstractNIC.config() available params:
    # mac - mac address in binary
    # max_clients - in AP mode, max number of clients
    # dhcp_hostname - set the hostname during dhcp requests
    # channel - wifi channel
    # password - wifi password
    # essid - SSID network name
    # auth_mode -
    # hidden - in AP mode, don't broadcast SSID ??
    #
    net_info['connected'] = sta_if.isconnected()
    # net_info['mode'] = sta_if.config('mode')[0]
    # net_info['interface'] = sta_if.config('mode')[1]
    net_info['mac'] = ompsh_binascii.hexlify(sta_if.config('mac'), ':').decode()
    # net_info['wifimode'] = sta_if.config('wifimode')[1]

    if net_info['connected']:
        net_info['auth_mode'] = sta_if.config('auth_mode')
        net_info['linkstatus'] = 'UP'
        net_info['ip'] = sta_if.ifconfig()[0]
        net_info['netmask'] = sta_if.ifconfig()[1]
        net_info['dns1'] = sta_if.ifconfig()[2]
        net_info['dns2'] = sta_if.ifconfig()[3]

    return net_info['connected']


def decode_http_header(hdr_obj):
    """
    Helper function for decoding HTTP headers
    :param hdr_obj: Header object to be decoded
    :return: a dictionary of the HTTP Header Key-value pairs
    """

    hdr_obj_txt = hdr_obj.decode()
    http_hdr = {}
    hline_count = 0
    for line in hdr_obj_txt.splitlines():
        if hline_count == 0:
            hstatus = line.split(' ')
            http_hdr['Version'] = hstatus[0]
            http_hdr['Code'] = hstatus[1]
            http_hdr['Status'] = ' '.join(hstatus[2:])
        else:
            try:
                hkey, hval = line.split(': ')
                http_hdr[hkey] = hval
                if hkey == 'Content-Type':
                    if hval == 'text/plain' or hval == 'text/html' or hval == 'text/html; charset=iso-8859-1':
                        http_hdr['File-Type'] = 'text'
                    else:
                        http_hdr['File-Type'] = 'binary'

            except ValueError:
                continue
        hline_count += 1

    return http_hdr


class MprShellCmd:

    ALL_CMDS = []

    def __init__(self):
        self.name = ''
        self.help = ''
        self.username = ''
        self.waiting_input = False
        self.input_line = ''
        self.input_echo = True
        self.output = []
        self.flags = {'error': ''}

    def stat_file(self, filename):

        fstat = {'is_file': False,
                 'is_dir': False,
                 'exists': False,
                 'error': 'No error',
                 'st_mode': 0,
                 'st_size': 0,
                 'st_size_help': '0B'
                 }
        try:
            sfile = os.stat(filename)
            fstat['st_mode'] = sfile[0]
            fstat['st_size'] = sfile[6]
            fstat['exists'] = True
            if 16384 <= sfile[0] < 32768:
                fstat['is_dir'] = True
            elif sfile[0] >= 32768:
                fstat['is_file'] = True

            if 0 < fstat['st_size'] < 1000:
                fstat['st_size_help'] = '{:.1f}B'.format(fstat['st_size']/1.0)
            elif 1000 <= fstat['st_size'] < 1000000:
                fstat['st_size_help'] = '{:.1f}K'.format(fstat['st_size']/1000.0)
            elif fstat['st_size'] >= 1000000:
                fstat['st_size_help'] = '{:.1f}M'.format(fstat['st_size']/1000000.0)
            elif fstat['st_size'] != 0:
                fstat['st_size_help'] = '{0}?'.format(fstat['st_size'], '?')

        except OSError:
            fstat['exists'] = False
            fstat['error'] = 'No such file or directory: {0}'.format(filename)
            #print('No such file or directory:', filename)

        return fstat

    def find_flags(self, cflags, cargs):
        for carg in cargs:
            if carg.startswith('-'):
                _, cf = carg.split('-')
                if cf in cflags:
                    cflags[cf] = True
                else:
                    # print('Invalid flag:', cf)
                    # self.output.append('Invalid flag: {0}'.format(cf))
                    self.flags['error'] = 'Invalid flag: {0}'.format(cf)
                    return False
                cargs.remove(carg)

        # print('Cflags:', cflags, 'Cargs:',cargs)
        return True

    def cmd_run(self):
        return True

    def cmd_input(self, cmd_input_args):
        pass

    def cmd_help(self):
        print('Cmds:', self.ALL_CMDS)


class CmdWGET(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'wget'
        self.help = 'retrieve a file over http'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def _do_wget(self, url, wget_file):

        _, _, wget_host, wget_path = url.split('/', 3)
        wget_url = 'GET /{0} HTTP/1.0\r\nHost: {1}\r\n\r\n'.format(wget_path, wget_host)
        wget_addr = ompsh_socket.getaddrinfo(wget_host, 80)[0][-1]
        wget_s = ompsh_socket.socket()
        wget_s.connect(wget_addr)
        wget_s.send(bytes(wget_url, 'utf8'))
        d_data = b''
        header = ''
        wget_valid = False
        wget_hdr = {}

        while True:
            buff_data = wget_s.recv(1000)
            if buff_data:
                if header == '':
                    header, d_data = buff_data.split(b'\r\n\r\n')
                    wget_hdr = decode_http_header(header)
                    if wget_hdr['Status'] == 'OK' and wget_hdr['Code'] == '200':
                        if wget_hdr['File-Type'] == 'text':
                            f = open(wget_file, 'w')
                        else:
                            f = open(wget_file, 'wb')
                        wget_valid = True

                    else:
                        break

                else:
                    d_data = buff_data

                if wget_hdr['File-Type'] == 'text':
                    url_data = d_data.decode()
                else:
                    url_data = d_data

                if wget_valid:
                    f.write(url_data)

            else:
                if wget_valid:
                    f.close()
                break

        wget_s.close()
        return wget_valid, wget_hdr

    def cmd_run(self, cargs=None):
        if len(cargs) == 0:
            return True

        if HAVE_NET is False:
            self.output.append('Networking stack not functional or disabled')
            return False

        wtoks = cargs[0].split('/')
        if len(wtoks) < 2:
            self.output.append('Invalid url: {0}'.format(cargs[0]))
            return False

        if not net_ioctl(None):
            self.output.append('Not Connected')
            return False

        wget_retval, wget_hdr = self._do_wget(cargs[0], wtoks[-1])
        if wget_retval is True:
            self.output.append('Retrieved as file: {0}'.format(wtoks[-1]))
        else:
            self.output.append('Couldnt retrieve, HTTP header Dump:')
            [self.output.append('{0} = {1}'.format(wk, wv)) for wk, wv in wget_hdr.items()]

        return wget_retval


class CmdIFCONFIG(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'ifconfig'
        self.help = 'prints network information'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):

        if HAVE_NET is False:
            self.output.append('Networking stack not functional or disabled')
            return False

        idata = {}
        net_ioctl(idata)
        ot = 'Active: {0}\n{1} <{2}>\ninet {3} netmask {4}\nether {5}'.format(idata['active'], idata['interface'],
                                                                 idata['linkstatus'],idata['ip'],
                                                                 idata['netmask'], idata['mac'])
        self.output.append(ot)

        return True


class CmdUNAME(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'uname'
        self.help = 'prints the system information'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        self.output.append('Platform={0}'.format(sys.platform))
        self.output.append('Python={0}'.format(sys.version))
        self.output.append('Implementation={0} {1}.{2}.{3}'.format(sys.implementation.name,
                                                                   sys.implementation.version[0],
                                                                   sys.implementation.version[1],
                                                                   sys.implementation.version[2]))
        try:
            self.output.append('Uname={0}'.format(' '.join(os.uname())))
        except AttributeError:
            pass

        return True


class CmdRM(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'rm'
        self.help = 'removes a file or directory'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        if len(cargs) == 0:
            return True

        file_info = self.stat_file(cargs[0])
        if not file_info['exists']:
            self.output.append(file_info['error'])
            return False

        elif file_info['is_dir']:
            try:
                os.rmdir(cargs[0])
                return True
            except OSError:
                self.output.append('Couldnt remove directory: {0}'.format(cargs[0]))
                return False

        elif file_info['is_file']:
            try:
                os.remove(cargs[0])
                return True
            except OSError:
                self.output.append('Couldnt remove file: {0}'.format(cargs[0]))
                return False
            # print('Not a directory:', directory[0])

        return False


class CmdMKDIR(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'mkdir'
        self.help = 'creates a directory'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        if len(cargs) == 0:
            return True

        file_info = self.stat_file(cargs[0])
        if file_info['exists']:
            self.output.append('Already exists: {0}'.format(cargs[0]))
            return False

        else:
            try:
                os.mkdir(cargs[0])
                return True
            except OSError:
                self.output.append('Couldnt make directory: {0}'.format(cargs[0]))
                return False


class CmdCD(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'cd'
        self.help = 'change directory'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        if len(cargs) == 0:
            return True

        file_info = self.stat_file(cargs[0])
        if not file_info['exists']:
            self.output.append(file_info['error'])

        elif file_info['is_dir']:
            os.chdir(cargs[0])
            return True

        elif file_info['is_file']:
            self.output.append('Not a directory: {0}'.format(cargs[0]))
            return False
            # print('Not a directory:', directory[0])

        return False


class CmdCAT(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'cat'
        self.help = 'prints a file to the screen'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        if len(cargs) == 0:
            self.output.append('Please specify a file')
            return False

        file_info = self.stat_file(cargs[0])
        if not file_info['exists']:
            self.output.append(file_info['error'])
            return False

        elif file_info['is_file']:
            with open(cargs[0], 'r') as catf:
                [self.output.append(x) for x in catf.read().splitlines()]

            return True

        elif file_info['is_dir']:
            self.output.append('Cant cat a directory: {0}'.format(cargs[0]))
            return False
            # print('Not a directory:', directory[0])

        return False


class CmdLS(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'ls'
        self.help = 'lists files on disk'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)
        self.flags['l'] = False

    def ll_dir(self, ls_dir):
        ll_output = []

        for lsdir_file in os.listdir(ls_dir):
            lsdir_file_info = self.stat_file('{0}/{1}'.format(ls_dir, lsdir_file))

            if lsdir_file_info['is_file']:
                ll_output.append('file {0} {1}'.format(lsdir_file_info['st_size_help'], lsdir_file))
            elif lsdir_file_info['is_dir']:
                ll_output.append('dir  {0} {1}'.format(lsdir_file_info['st_size_help'], lsdir_file))

        return ll_output

    def cmd_run(self, cargs=None):
        self.flags['l'] = False
        ls_list = []

        if not self.find_flags(self.flags, cargs):
            self.output.append(self.flags['error'])
            return False

        if len(cargs) == 0:
            ls_list.append(os.getcwd())
        else:
            ls_list = cargs.copy()

        for ls_file in ls_list:

            file_info = self.stat_file(ls_file)

            if not file_info['exists']:
                self.output.append(file_info['error'])
                return False

            if file_info['is_file']:
                if self.flags['l']:
                    self.output.append('file {0} {1}'.format(file_info['st_size_help'], ls_file))
                else:
                    self.output.append(ls_file)

            elif file_info['is_dir']:
                if self.flags['l']:
                    ll_output = self.ll_dir(ls_file)
                    [self.output.append(x) for x in ll_output]
                else:
                    [self.output.append(x) for x in os.listdir(ls_file)]


class CmdPWD(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'pwd'
        self.help = 'prints the current working directory'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        self.output.append(os.getcwd())


class CmdWHOAMI(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'whoami'
        self.help = 'prints your username'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        self.output.append(self.username)


class CmdDF(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'df'
        self.help = 'prints disk usage'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):

        mnt_pt = '/'
        f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, _, _, _, _, f_namemax = os.statvfs('/')
        if f_bsize == 0:
            for rdir in os.listdir('/'):
                mnt_pt = '/' + rdir
                f_bsize, f_frsize, f_blocks, f_bfree, f_bavail, _, _, _, _, f_namemax = os.statvfs(mnt_pt)

        self.output.append("Filesystem\tSize\tUsed\tAvail\tUse%")
        fs_size = f_blocks * f_frsize
        fs_avail = f_bfree * f_bsize
        fs_used = fs_size - fs_avail
        fs_used_perc = fs_used / fs_size

        self.output.append('{}\t\t{:.1f}M\t{:.1f}M\t{:.1f}M\t{:.0%}'.format(mnt_pt, fs_size/1000000.0,
                                                                   fs_used/1000000.0, fs_avail/1000000.0, fs_used_perc))


class CmdMEMINFO(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'meminfo'
        self.help = 'prints memory usage'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        self.output.append(micropython.mem_info())


class CmdPASSWD(MprShellCmd):

    def __init__(self, cmd_username):
        super().__init__()
        self.name = 'passwd'
        self.help = 'changes password for current user'
        self.username = cmd_username
        self.ALL_CMDS.append(self.name)

    def cmd_run(self, cargs=None):
        self.waiting_input = True
        self.input_echo = False
        # print(cargs)
        # cargs['user'] = 'bob'
        self.input_line = 'Enter password for {0}:'.format(self.username)

    def cmd_input(self, cmd_input_args):
        self.waiting_input = False
        self.input_line = ''
        # print(cmd_input_args)
        self.output.append('Setting password for {0} to {1}'.format(self.username, cmd_input_args))


class MprShell:

    cmds = {}

    def __init__(self, prompt='mprsh#', username='console'):
        self.prompt = prompt
        self.username = username
        self.started = False
        self.cmd_output = []
        self.cmd_cur = []
        self.cmd_hist = []
        self.input_echo = True
        self.need_input = False
        self.input_cmd = ''
        self.input_prompt = ''
        self.shell_env = {}

    def start_shell(self, username='noone', prompt='mprsh#'):
        self.started = True
        self.username = username
        self.prompt = prompt

        self.shell_env['user'] = self.username
        self.shell_env['cwd'] = os.getcwd()
        self.shell_env['prompt'] = self.prompt

        self.cmds['whoami'] = CmdWHOAMI(cmd_username=self.username)
        self.cmds['ls'] = CmdLS(cmd_username=self.username)
        self.cmds['pwd'] = CmdPWD(cmd_username=self.username)
        self.cmds['cd'] = CmdCD(cmd_username=self.username)
        self.cmds['uname'] = CmdUNAME(cmd_username=self.username)
        self.cmds['rm'] = CmdRM(cmd_username=self.username)
        self.cmds['rmdir'] = CmdRM(cmd_username=self.username)
        self.cmds['mkdir'] = CmdMKDIR(cmd_username=self.username)
        self.cmds['wget'] = CmdWGET(cmd_username=self.username)
        self.cmds['passwd'] = CmdPASSWD(cmd_username=self.username)
        self.cmds['cat'] = CmdCAT(cmd_username=self.username)
        self.cmds['ifconfig'] = CmdIFCONFIG(cmd_username=self.username)
        self.cmds['meminfo'] = CmdMEMINFO(cmd_username=self.username)
        self.cmds['df'] = CmdDF(cmd_username=self.username)

    def run_cmd(self, scmd):
        # scmd_args = re.split(" +", scmd)

        self.cmd_output.clear()
        if not self.started:
            self.start_shell()

        if len(scmd) == 0:
            return True

        if self.need_input:
            scmd_args = [self.input_cmd, scmd]
        else:
            if scmd == 'exit':
                self.started = False
                return False

            if scmd == 'help':
                [self.cmd_output.append('{0} - {1}'.format(x, self.cmds[x].help)) for x in list(self.cmds)]
                self.cmd_output.append('help - displays list of shell commands')
                self.cmd_output.append('exit - exits shell')
                return True

            scmd_args = scmd.split()
            # print('Received cmd:', scmd_args[0], ' with args:', scmd_args[1:])

        if self.need_input or scmd_args[0] in self.cmds:

            '''
            try:
                if self.need_input:
                    self.cmds[self.input_cmd].cmd_input(scmd_args[1:])
                else:
                    self.cmds[scmd_args[0]].cmd_run(scmd_args[1:])

                self.cmd_output = self.cmds[scmd_args[0]].output.copy()
                self.cmds[scmd_args[0]].output.clear()
            except:
                self.cmd_output.append('Error running shell cmd: {} {}'.format(scmd, sys.print_exception(0))
            '''
            if self.need_input:
                self.cmds[self.input_cmd].cmd_input(scmd_args[1:])
            else:
                self.cmds[scmd_args[0]].cmd_run(scmd_args[1:])

            self.cmd_output = self.cmds[scmd_args[0]].output.copy()
            self.cmds[scmd_args[0]].output.clear()
            # print(self.cmd_output)

            if self.cmds[scmd_args[0]].waiting_input:
                self.need_input = True
                self.input_cmd = scmd_args[0]
                self.input_prompt = self.cmds[scmd_args[0]].input_line
                self.input_echo = self.cmds[scmd_args[0]].input_echo
            else:
                self.need_input = False
                self.input_cmd = ''
                self.input_prompt = ''
                self.input_echo = True

        else:
            self.cmd_output.append('Unknown command: {0}'.format(scmd_args[0]))
            # print('Unknown command:', scmd_args[0])

        return True


def run():

    rs = MprShell()
    rs.start_shell()

    while True:

        if rs.need_input:
            icmd = input(rs.input_prompt)
        else:
            icmd = input(rs.prompt)

        if len(icmd) > 0:
            if not rs.run_cmd(icmd):
                return

            for oline in rs.cmd_output:
                print(oline)

            gc.collect()


if __name__ == '__main__':
    run()

