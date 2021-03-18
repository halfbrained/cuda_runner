import os
import sys
import re
import json
import subprocess
import queue # import Queue, Empty
import time
from fnmatch import fnmatch
from threading import Thread

from cudatext import *
from cudax_lib import _json_loads, log
import cuda_project_man as p

from cudax_lib import get_translation
_   = get_translation(__file__)  # I18N

""" file:///install.inf
"""

IS_WIN = os.name=='nt'
IS_MAC = sys.platform=='darwin'
IS_LIN = not IS_WIN and not IS_MAC
OS_KEY = 'windows' if IS_WIN else ('osx' if IS_MAC else 'linux')
BUILDS_DIR = os.path.join(app_path(APP_DIR_DATA), 'buildsystems')
BUILD_TOOLS_DIR = BUILDS_DIR
USER_DIR = os.path.expanduser('~')
PROJECT = p.global_project_info

option_max_logs = 8
LEXMAP = {} # lexer name -> build name
EXTMAP = {} # ^ same for files (assigning build-config to file if no lexer)
SUBCOMMANDS = {} # 'my cpp build command name' ->  'build cfg name|command name'
BUILD_LOG_START = [ # added: $build_name, $start_time, $duration, $return_code
    _('-- [${start_time}] Building: ${build_name}: ${file_name}'),
    _('-- Command: ${cmd}'),
    _('-- Working dir: ${working_dir}'),
]
BUILD_LOG_FINISH = [ 
    _('-- Done (${duration}s), return code: ${return_code}'),
]

MAIN_CMD_NAME = _('Build')

fn_config = os.path.join(app_path(APP_DIR_SETTINGS), 'cuda_runner.json')

'!!! undo log'
LOG = True


def get_first(gen, notnone=False):
    try:
        if notnone:
            for val in gen:
                if val is not None:
                    return val
        else:
            return next(gen)
    except StopIteration:
        pass
    return None

def collapse_path(path):
    if (path + os.sep).startswith(USER_DIR + os.sep):
        path = path.replace(USER_DIR, '~', 1)
    return path

def set_output(lines):
    app_log(LOG_CLEAR, '', panel=LOG_PANEL_OUTPUT)
    app_proc(PROC_BOTTOMPANEL_ACTIVATE, 'Output')

    for line in lines:
        app_log(LOG_ADD, line, panel=LOG_PANEL_OUTPUT)
        
def set_output_regex(regex):
    if regex:
        app_log(LOG_SET_REGEX, regex)
        app_log(LOG_SET_LINE_ID, '2', panel=LOG_PANEL_OUTPUT)
        app_log(LOG_SET_COL_ID, '3', panel=LOG_PANEL_OUTPUT)
        app_log(LOG_SET_NAME_ID, '1', panel=LOG_PANEL_OUTPUT) # filename


class Command:
    def __init__(self):
        self.buildings = [] # new are appended
        
        self.current_build_log = None # for going through list of oputputs
        
        self.load_config()
        
        self._builds = [] # for property .builds
        self._builds_loaded = False
            
        if SUBCOMMANDS:
            subcmds = '\n'.join('{}\t{}'.format(name, val)  for name,val in SUBCOMMANDS.items())
            app_proc(PROC_SET_SUBCOMMANDS, 'cuda_runner;build_subcommand;'+subcmds)
    
    @property
    def builds(self):
        if not self._builds_loaded:
            self._load_builds()
        return self._builds
            
    def _load_builds(self):
        self._builds_loaded = True
        for name in os.listdir(BUILDS_DIR):
            if name.endswith('.sublime-build'):
                path = os.path.join(BUILDS_DIR, name)
                try:
                    build = Build(path)
                except NotImplementedError as ex:
                    print(_('Failed to load build-system "{}": {}: {}').format(name, type(ex).__name__, ex))
                    continue
                except Exception as ex:
                    msg_box(_('Failed to load build-system "{}": {}: {}').format(name, type(ex).__name__, ex), MB_ICONWARNING)
                    continue
                    
                self._builds.append(build)
        self._builds.sort(key=lambda b: b.name.lower())
            
    def load_config(self):
        global option_max_logs
        
        if os.path.exists(fn_config):
            with open(fn_config, 'r', encoding='utf-8') as f:
                j = json.load(f)
            maps = {    
                'lexmap':LEXMAP, 
                'extmap':EXTMAP, 
                'subcommands':SUBCOMMANDS
            }
            lists = {   
                'build_log_start_info':BUILD_LOG_START, 
                'build_log_finish_info':BUILD_LOG_FINISH
            }
            
            ## load
            option_max_logs = max(1, j.get('max_logs', option_max_logs))
            
            for name,mp in maps.items(): # dicts
                if name in j:
                    mp.clear()
                    mp.update(j[name])
            for name,l in lists.items(): # lists
                if name in j:
                    l.clear()
                    l.extend(j[name])

                
    def save_config(self):
        j = {   
            'max_logs': option_max_logs,
            'lexmap':LEXMAP, 
            'extmap':EXTMAP, 
            'subcommands':SUBCOMMANDS,
            'build_log_start_info':BUILD_LOG_START, 
            'build_log_finish_info':BUILD_LOG_FINISH,
        }
        with open(fn_config, 'w', encoding='utf-8') as f:
            json.dump(j, f, indent=2)
        
    def config(self):
        if not os.path.exists(fn_config):
            self.save_config()
        file_open(fn_config)
        
    def on_start(self, ed_self): # subcommand hotkeys dont work without this
        pass
        
    def on_open(self, ed_self):
        if not self._builds_loaded:
            self._load_builds()
        
    def on_exit(self, ed_self):
        self.cancel_build()

    def build(self, name=MAIN_CMD_NAME):
        pass;               LOG and log('.build({})'.format(name))
        
        if not ed.get_filename():
            msg_status(_('Save document to disk before building'))
            return

        b = self._get_ed_build(ed)
        if not b:
            lex = ed.get_prop(PROP_LEXER_FILE)
            if lex:
                msg = _('No build-system(s) found for lexer ') + lex
            else:
                msg = _('No build-system(s) found for file ') + os.path.basename(ed.get_filename())
            msg_status(msg)
            return
        
        if name is None:
            cmd_names = b.list_commands()
            ind = dlg_menu(DMENU_LIST, cmd_names)
            if ind is None:
                return
            name = cmd_names[ind]
        
        self._run_build_cmd(b, name)
        
    def cmds_menu(self):
        self.build(name=None)
        
    def cancel_build(self):
        if self.buildings:
            self.buildings[-1].cancel()
        
    def build_subcommand(self, arg):
        bname,cmdname = [spl.strip() for spl in arg.split('|')]
        if bname.endswith('.sublime-build'):
            bname = bname.replace('.sublime-build', '')
        
        b = self._getbuild(bname)
        if b is None:
            msg_status(_('No such build-system: ')+bname)
            return
    
        self._run_build_cmd(b, cmdname)
        
    def next_output(self):
        self._show_output(direction=+1)
        
    def prev_output(self):
        self._show_output(direction=-1)
    
    def lexmap_cfg(self):
        lex = ed.get_prop(PROP_LEXER_FILE)
        filepath = ed.get_filename()
        if not filepath: # cant build if not a file ... TODO?
            msg_status(_('Save document to disk before building'))
            return
        elif lex: # associate to lexer if have one, file otherwise
            mp = LEXMAP
            key = lex
            caption = _('Choose build-system for lexer: ')+lex
        elif filepath:
            fn = os.path.basename(filepath)
            spl = fn.split('.')
            if len(spl) > 2: #double+.ext
                exts = ['*.'+'.'.join(spl[-i:]) for i in range(1, 1+len(spl)-1)]
                ind = dlg_menu(DMENU_LIST, exts, caption=_('Choose extention for association'))
                if ind is None:
                    return
                key = exts[ind]
            elif len(spl) == 2: # filename.ext
                key = '*.'+spl[-1]
            else: # no ext
                key = collapse_path(filepath) # full path
            
            mp = EXTMAP
            caption = ('Choose build-system for file-type: ')+key
            
        # fill list
        build_names = []
        if key in mp:
            build_names.append('<None>')
        build_names.extend( b.name for b in self.builds )
        
        # find focused (current build-system)
        try:
            focused = build_names.index(mp.get(key))
        except ValueError:
            focused = 0
        
        ind = dlg_menu(DMENU_LIST, build_names, focused=focused, caption=caption)
        if ind == 0 and build_names[0] == '<None>':
            del mp[key]
        elif ind is not None:
            mp[key] = build_names[ind]
            
        self.save_config()
        
    
    def _run_build_cmd(self, build, cmdname):
        cmd_names = build.list_commands()
        if cmdname not in cmd_names:
            msg_status(_('No command "{}" in build-system "{}"').format(cmdname, build.name)
                        +':...\n  {}'.format('\n  '.join(cmd_names)))
            return
            
        r = build.run_cmd(cmdname)
        if r is None:
            msg_status(_('Failed to run command "{}" in build-system "{}"').format(cmdname, build.name))
            return
        popen, cmdj = r

        f_can_print = lambda bld: self.current_build_log is bld
        building = Building(popen, build.name, cmdj, f_can_print=f_can_print)
        self._on_new_building(building)
        building.start()  # start() needs to be after _on_new_building() 
        
    def _on_new_building(self, building):
        self.buildings.append(building)
        self.current_build_log = building
        
        # limit build-logs count
        if len(self.buildings) > option_max_logs:
            del self.buildings[:-option_max_logs]
        
    def _get_ed_build(self, ed):
        filepath = ed.get_filename()
        if not filepath:
            return
        
        # custom file-type association
        ext_masks = list(EXTMAP)
        ext_masks.sort(key=lambda s: len(s), reverse=True) # from most specific
        bnames = (EXTMAP[mask] for mask in ext_masks  if fnmatch(filepath, mask)) # matching build-names
        # might be associated to missing build.. search
        build = get_first((self._getbuild(bname) for bname in bnames), notnone=True) 
        if build:
            pass;               LOG and log('build match: ext: {}'.format(build.name))  
            return build
            
        # custom lexer association
        edlex = ed.get_prop(PROP_LEXER_FILE)
        if edlex and edlex in LEXMAP:
            build = self._getbuild(LEXMAP[edlex])
            if build:
                pass;               LOG and log('build match: lex: {}'.format(edlex))  
                return build
        
        # sublime selectors
        for b in self.builds:
            if b.match_ed(ed):
                return b
        
    def _getbuild(self, name):
        return get_first(b for b in self.builds  if b.name == name)
        
    def _show_output(self, direction):
        """ direction: -1 = older;  +1 = newer
        """
        if not self.buildings:
            msg_status(_('No builds done yet'))
            return

        try:
            ind = self.buildings.index(self.current_build_log)
            newind = ind + direction
        except:
            newind = 0 # show first if not 
        
        if newind < 0:
            msg_status(_('No older build log present: {}/{}').format(ind+1, len(self.buildings)))
            return
        elif newind >= len(self.buildings):
            msg_status(_('No newer build log present: {}/{}').format(ind+1, len(self.buildings)))
            return
        
        msg_status(_('Showing build log: {}/{}').format(newind+1, len(self.buildings)))
        
        self.current_build_log = self.buildings[newind]
        
        set_output(self.current_build_log.lines)
        set_output_regex(self.current_build_log.cmdj.get('file_regex'))        
    
class Build:
    # http://www.sublimetext.com/docs/3/build_systems.html#custom_options
    # All build systems may use the following top-level keys in the .sublime-build file. 
    OPTIONS = {
        'selector',
        'file_patterns', # :["*.py"]
        'keyfiles',     # files to trigger this build, : ["Makefile"].
        'variants',     # list of subsidiary build systems that will inherit the options from the top-level; has 'name'
        'cancel',
        'target',       # 'Command' to run when the build system is invoked.
    
        'windows',
        'osx',
        'linux',
    }
    TARGET_OPTIONS = {
        'cmd',
        'shell_cmd',    # cmd + piping etc
        'working_dir',
        'file_regex',   # output result navigation regex
                        #     1:filename, 2:line number, 3:column number, 4:message
        'line_regex',   # ^~
        'encoding',
        'env',          # environment vars
        'quiet',        # reduce output volume
        'word_wrap',    # enables in output
        'syntax',       # ~lexer for output
        
        'shell',        # not in spec, used in configs
    }
    EXPANDABLE_OPTIONS = [
        'cmd',
        'shell_cmd',    # cmd + piping etc
        'working_dir',
    ]
    
    def __init__(self, path):
        self._load(path)
        self.name = os.path.splitext(os.path.basename(path))[0]
        
    def _load(self, path):
        with open(path, 'r', encoding='utf-8') as f:
            txt = f.read()
            
        # remove stream comments: /* ... */
        if '/*' in txt:
            txt = re.sub('/\*.*?\*/', '', txt, flags=re.DOTALL)  # all done consecutively once, no need to compile
        if '\ ' in txt: # json chokes on escaped spaces
            txt = txt.replace('\ ', ' ')
            
        self.j = _json_loads(txt)
        if self.j is None:
            raise Exception(_('Json Error'))
        if 'target' in self.j:
            raise NotImplementedError(_('"target" option is not supported')) # work done in ST python-plugin
        
        self._load_selectors()
        
    def _load_selectors(self):
        self.file_patterns = self.j.get('file_patterns', [])
        sel_s = self.j.get('selector', '')
        
        if sel_s:
            sel = re.sub('[,|]', ' ', sel_s) # handle multiple-selector-string
            spls = (spl.strip() for spl in sel.split(' '))
            self.selectors = [spl.split('.')[1] for spl in spls  if spl and sel and not sel.startswith('-')]
        else:  
            self.selectors = {}
        
        
    def list_commands(self):
        cmds = []
        
        cmd_opts = ['cmd', 'shell_cmd']
        # have main cmd or a variant with cmd
        cmdj = self._get_cmd(MAIN_CMD_NAME)
        if 'cmd' in cmdj  or  'shell_cmd' in cmdj:
            cmds.append(MAIN_CMD_NAME) 
            
        # variants
        for variant in self.j.get('variants', []):
            name = variant.get('name', '-')
            cmdj = self._get_cmd(name)
            if 'cmd' in cmdj  or  'shell_cmd' in cmdj:
                cmds.append(name)
        
        return cmds
        
    def match_ed(self, ed):
        """ returns: bool - is appropriate for specified Editor
            * Checks: 
                'selector', 'file_patterns'   
        """
        fn = ed.get_filename()
        if fn and self.file_patterns:
            if any(fnmatch(name=fn, pat=pattern) for pattern in self.file_patterns):
                pass;               LOG and log('build match: inbuild: file({}): {}'.format(fn, self.name))
                return True
                
        lex = ed.get_prop(PROP_LEXER_FILE)
        if lex and self.selectors:
            lex = lex.lower()
            for sel in self.selectors:
                if lex == sel:
                    pass;               LOG and log('build match: inbuild: lex: {}'.format(sel))
                    return True
                
        return False
    
    def run_cmd(self, cmdname):
        cmdj = self._get_cmd(cmdname)
        cmdj = self._expand_cmd(cmdj)
        
        cmd = cmdj.get('shell_cmd')  or cmdj.get('cmd')
        is_shell = cmdj['shell']  if 'shell' in cmdj else  'shell_cmd' in cmdj
        cwd = cmdj.get('working_dir')
        file_regex = cmdj.get('file_regex')  
        env = cmdj.get('env')
        
        set_output_regex(file_regex)
        
        pass;                   LOG and log('?? Popen cmd={}', cmd)
        try:
            cmd_str = ' '.join(cmd) if type(cmd) == list else cmd
            msg_status(_('Running: "{}"').format(cmd_str))
            popen = subprocess.Popen(
                        cmd,
                        stdout = subprocess.PIPE,
                        stderr = subprocess.STDOUT,
                        shell = is_shell,
                        env = env,
                        cwd = cwd,
            )
        except Exception as ex:
            msg_box('{}: {}'.format(type(ex).__name__, ex), MB_ICONWARNING)
            log('fail Popen',)
            return
        if popen is None:
            pass;               LOG and log('fail Popen',)
            msg_status(_('Fail running: {}').format(cmd))
            return
        pass;                  LOG and log('ok Popen',)

        app_log(LOG_CLEAR, '', panel=LOG_PANEL_OUTPUT)

        return popen, cmdj
    
    def _get_cmd(self, cmdname):
        def get_cmd(j): #SKIP
            """get relevant values + values from OS part"""
            d = {k:v for k,v in j.items()  if k in Build.TARGET_OPTIONS}
            if OS_KEY in j:
                os_d = {k:v for k,v in j.get(OS_KEY, {}).items()  if k in Build.TARGET_OPTIONS}
                d.update(os_d)
            return d
            
        if cmdname == MAIN_CMD_NAME:
            cmdj = self.j
        else:
            try:
                cmdj = next(variant for variant in self.j.get('variants', {})  if variant.get('name') == cmdname)
            except StopIteration:
                raise Exception(_('No such command: ')+cmdname)
            
        cmdj = get_cmd(cmdj)
        return cmdj
        
    def _expand_cmd(self, cmdj):
        # expand vars
        for exopt in Build.EXPANDABLE_OPTIONS:
            if exopt in cmdj:
                cmdj[exopt] = expandvars(cmdj[exopt])

        return cmdj
        

class Building:
    def __init__(self, popen, build_name, cmdj, f_can_print):
        self.build_name = build_name
        self.cmdj = cmdj
        self.f_can_print = f_can_print
        self.readthread = ReadThread(popen, cmdj.get('encoding') or 'utf-8')
        self.lines = []
        
        self.quiet = self.cmdj.get('quiet', False) # disable extra build info 
        
        # current values for log
        self._vars_snap = {k:(v() if callable(v) else v)  for k,v in VAR_EXPAND_MAP.items()}
        
        self._is_finished = False
        self._is_canceled = False
        
    def start(self):
        self.readthread.start()
        
        self._start_time = time.time()
        self._start_time_str = time.strftime('%H:%M:%S')
        self.focused_log = False
        
        timer_proc(TIMER_START, self._on_timer, 200, tag='')

        if BUILD_LOG_START:
            self._output_add_meta(BUILD_LOG_START)        
    
    @property
    def returncode(self):
        return self.readthread.returncode
    
    def cancel(self):
        if not self._is_finished and not self._is_canceled:
            pass;               LOG and log('* cancelling building: finished:{}'.format(self._is_finished))
            self._is_canceled = True
            self._stop()
            
            cancel_line = _('-- Canceled')
            self.lines.append(cancel_line)
            if self.f_can_print(self):
                app_log(LOG_ADD, cancel_line, panel=LOG_PANEL_OUTPUT)
            
    
    def _on_timer(self, tag='', info=''):
        while not self.readthread.q.empty():
            try:
                line = self.readthread.q.get_nowait()
            except queue.Empty:
                break
                
            if line is None:
                self._is_finished = True
                self._stop()
                
                if BUILD_LOG_FINISH:
                    self._output_add_meta(BUILD_LOG_FINISH)
                break
                
            self.lines.append(line)
            if self.f_can_print(self):
                app_log(LOG_ADD, line, panel=LOG_PANEL_OUTPUT)
            
            if not self.focused_log: # activate panel once
                self.focused_log = True
                app_proc(PROC_BOTTOMPANEL_ACTIVATE, 'Output')
                
         
    def _stop(self):
        pass;               LOG and log('* Finished Building')

        timer_proc(TIMER_STOP, self._on_timer, 0)

        self.readthread.m_stop()

    def _output_add_meta(self, lines):
        if self.quiet:
            return
        
        values = { 
            **self._vars_snap, 
            **{'$'+k:str(v) for k,v in self.cmdj.items()},
            
            '$build_name': self.build_name,
            '$start_time': self._start_time_str,
            '$duration': lambda: '{:.1}'.format(self.readthread.end_time - self._start_time),
            '$return_code': lambda: self.returncode,
        }
        
        for line in lines:
            line = expandvars(line, mp=values, no_match_val='[None]')
            
            if self.f_can_print(self):
                app_log(LOG_ADD, line, panel=LOG_PANEL_OUTPUT)
            self.lines.append(line)
        
        
class ReadThread(Thread):
    def __init__(self, popen, encoding):
        Thread.__init__(self)
        self.q = queue.Queue() # None - ended
        self.stop = False
        self.popen = popen
        self.encoding = encoding or 'utf_8'
        
        self.returncode = None
        self.end_time = time.time()-1
        
    def run(self):
        while not self.stop:
            out_ln = self.popen.stdout.readline().decode(self.encoding)
            if len(out_ln) == 0:
                self.q.put(None)
                self.end_time = time.time()
                break
            out_ln = out_ln.strip('\r\n')
            
            self.q.put(out_ln)
            
    def m_stop(self):
        self.stop = True
        self.popen.kill()
        self.popen.wait()
        self.returncode = str(self.popen.returncode) # string - issues with zero in expandvars.repl
        

    
VAR_EXPAND_MAP = {
    # The path to the Packages/ folder 
    '$packages':            BUILD_TOOLS_DIR,
    # A string containing the platform Sublime Text is running on: windows, osx or linux. 
    '$platform':            OS_KEY,
    
    # The full path, including folder, to the file in the active view. 
    '$file':                lambda: ed.get_filename(),
    # The path to the folder that contains the file in the active view. 
    '$file_path':           lambda: os.path.dirname(ed.get_filename()),
    # The file name (sans folder path) of the file in the active view. 
    '$file_name':           lambda: os.path.basename(ed.get_filename()),
    # The file name, exluding the extension, of the file in the active view. 
    '$file_base_name':      lambda: os.path.splitext(os.path.basename(ed.get_filename()))[0],
    # The extension of the file name of the file in the active view. 
    '$file_extension':      lambda: os.path.splitext(os.path.basename(ed.get_filename()))[1],
    # The full path to the first folder open in the side bar. 
    '$folder':              lambda: os.path.dirname(PROJECT.get('mainfile', '')), # closest: project mainfile dir
    
    # The full path to the current project file. 
    '$project':             lambda: PROJECT.get('filename'),
    # The path to the folder containing the current project file. 
    '$project_path':        lambda: os.path.dirname(PROJECT.get('filename', '')),
    # The file name (sans folder path) of the current project file. 
    '$project_name':        lambda: os.path.basename(PROJECT.get('filename', '')),
    # The file name, excluding the extension, of the current project file. 
    '$project_base_name':   lambda: os.path.splitext(os.path.basename(PROJECT.get('filename', '')))[0],
    # The extension of the current project file. 
    '$project_extension':   lambda: os.path.splitext(os.path.basename(PROJECT.get('filename', '')))[1],
}    
re_expand = re.compile('(?<!\\\)(\$[a-z_]+|\$\{[^}]+\}*)')

def expandvars(s, mp=VAR_EXPAND_MAP, no_match_val=None):
    def repl(match): #SKIP
        s = match.group(0)
        r = s.replace('{', '').replace('}', '').replace('$', '')
        rs = [('$'+var) for var in r.split(':')]

        for optname in rs:
            val = mp.get(optname)
            try:
                val = val()
            except TypeError:
                pass
            if val:
                return val
        return no_match_val or s
        
    def expand_str(s): #SKIP
        if '$' in s:
            return re_expand.sub(repl, s)
        else:
            return s
        
    if type(s) == str:
        return expand_str(s)
    else:
        return [expand_str(sp) for sp in s]
        
