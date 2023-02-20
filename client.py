import socket
import cmd2
import json
import readline
import os
import atexit
import threading

HEADER_LENGTH = 10
LVTYPE = 0
HVTYPE0 = 1
HVTYPE1 = 2

def listenloop(s):

    while (1):
        message = receive_message(s)
        if message is False:
            print('Closed connection')
            break
        else:
            app.terminal_lock.acquire()
            data = message["data"]
#            print(data)
            app.async_alert(str(json.loads(message["data"])["response"]))
            app.terminal_lock.release()


def receive_message(socket):

    try:

        # Receive our "header" containing message length, it's size is defined and constant
        message_header = socket.recv(HEADER_LENGTH)

        # If we received no data, client gracefully closed a connection, for example using socket.close() or socket.shutdown(socket.SHUT_RDWR)
        if not len(message_header):
            return False

        # Convert header to int value
        message_length = int(message_header.decode('utf-8').strip())

#        app.async_alert(str(message_length))

        # Return an object of message header and message data
        return {'header': message_header, 'data': socket.recv(message_length)}

    except:

        # If we are here, client closed connection violently, for example by pressing ctrl+c on his script
        # or just lost his connection
        # socket.close() also invokes socket.shutdown(socket.SHUT_RDWR) what sends information about closing the socket (shutdown read/write)
        # and that's also a cause when we receive an empty message
        return False



## ===========================================
## Execute commands
## ===========================================

class CmdLoop(cmd2.Cmd):
    """Example cmd2 application where we create commands that just print the arguments they are called with."""


    # Are this shortcuts necessary?
    def __init__(self,s):
        # Create command shortcuts which are typically 1 character abbreviations which can be used in place of a command. Leave as is
        shortcuts = dict(cmd2.DEFAULT_SHORTCUTS)
        shortcuts.update({'$': 'readvoltage', '%': 'readcurrent'})
        super().__init__(shortcuts=shortcuts)
        self.socket=s



    def send(self,data):
        serialized = json.dumps(data)
        msg = f"{len(serialized):<{HEADER_LENGTH}}"

        self.socket.send(bytes(msg,"utf-8"))
        self.socket.sendall(bytes(serialized,"utf-8"))



    # There has to be a command for every interaction we need. So, readvoltage, readcurrents, readtemps, etc.
    # Each one has to have its counterpart in commands.py




    # LV commands
    # ===========

    # powerOn()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOn(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : LVTYPE,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)
#        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # powerOff()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_powerOff(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : LVTYPE,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)

#        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # readvoltage()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readvoltage(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : LVTYPE,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)

#        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # readcurrent()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readcurrent(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : LVTYPE,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)

#        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # readtemp()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='LV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_readtemp(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : LVTYPE,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)

#        lvqueue.put([args.cmd2_statement.get().command, args.channel])


    # test()
    #pprint_parser = cmd2.Cmd2ArgumentParser()
    #pprint_parser.add_argument('-v', '--voltage', type=float, help='Volatge to ramp to')
    #pprint_parser.add_argument('-c', '--channel', type=int, help='Channel number')
    #@cmd2.with_argparser(pprint_parser)
    #def do_test(self, args):
    #    """Print the options and argument list this options command was called with."""
    #    lvqueue.put([args.cmd2_statement.get().command, args.channel, args.voltage])


    # HV commands
    # ===========

    # rampHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int,   help='HV channel number')
    pprint_parser.add_argument('-v', '--voltage', type=float, help='Voltage to ramp up to')
    @cmd2.with_argparser(pprint_parser)
    def do_rampHV(self, args):
        """Print the options and argument list this options command was called with."""

        data= {
            "type" : HVTYPE0 if args.channel<6 else HVTYPE1,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel,args.voltage]
        }
        self.send(data)


    # downHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='HV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_downHV(self, args):
        """Print the options and argument list this options command was called with."""

        data= {
            "type" : HVTYPE0 if args.channel<6 else HVTYPE1,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)



    # setHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int,   help='HV channel number')
    pprint_parser.add_argument('-v', '--voltage', type=float, help='Voltage to set')
    @cmd2.with_argparser(pprint_parser)
    def do_setHV(self, args):
        """Print the options and argument list this options command was called with."""

        data= {
            "type" : HVTYPE0 if args.channel<6 else HVTYPE1,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel,args.voltage]
        }
        self.send(data)


# these next two commands refer to channel as pico channel not HV channel (so 0 or 1).
# As it is written now, the argument is though still the HV channel
    # resetHV()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel', type=int, help='HV channel number')
    @cmd2.with_argparser(pprint_parser)
    def do_resetHV(self, args):
        """Print the options and argument list this options command was called with."""

        data= {
            "type" : HVTYPE0 if args.channel<6 else HVTYPE1,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel]
        }
        self.send(data)


    # setHVtrip()
    pprint_parser = cmd2.Cmd2ArgumentParser()
    pprint_parser.add_argument('-c', '--channel',   type=int, help='HV channel number')
    pprint_parser.add_argument('-T', '--trippoint', type=int, help='Trip point in nA')
    @cmd2.with_argparser(pprint_parser)
    def do_setHVtrip(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : HVTYPE0 if args.channel<6 else HVTYPE1,
            "cmdname": args.cmd2_statement.get().command,
            "args" : [args.channel,args.trippoint]
        }
        self.send(data)

    
    # data acquisition commands

    @cmd2.with_argparser(pprint_parser)
    def do_get_v48(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : LVTYPE,
            "cmdname": args.cmd2_statement.get().command,
            "args" : []
        }
        self.send(data)


    @cmd2.with_argparser(pprint_parser)
    def do_get_vhv1(self, args):
        """Print the options and argument list this options command was called with."""
        data= {
            "type" : HVTYPE0,
            "cmdname": args.cmd2_statement.get().command,
            "args" : []
        }
        self.send(data)








## Main function
## =============


if __name__ == '__main__':


    history_file = os.path.expanduser('.lvhv_history')
    if not os.path.exists(history_file):
        with open(history_file, "w") as fobj:
            fobj.write("")
    readline.read_history_file(history_file)
    atexit.register(readline.write_history_file, history_file)

    topdir = os.path.dirname(os.path.realpath(__file__))


    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    host = "127.0.0.1"
    port = 12000
    sock.connect((host,port))

    lvThrd = threading.Thread(target=listenloop, daemon = True, args=[sock])
    lvThrd.start()


    app = CmdLoop(sock)

#    lvThrd = threading.Thread(target=listenloop, daemon = True)
#    lvThrd.start()


    app.cmdloop()
