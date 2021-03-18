Plugin for CudaText.
Adds support for build-systems from Sublime Text 3. It runs external tools, using
configurations stored in ST3's build-systems, files with .sublime-build extension.
Only those build-systems are supported that do not require additional Python code
(Python code in ST3 plugin which contained that build-system).

Build-system files must be copied to [CudaText]/data/buildsystems folder.
Sometimes ST3 packages with build-systems include also binaries (.exe files).
These binaries must be copied to [CudaText]/data/buildsystems/tools folder.

Commands
--------

Plugin gives commands in the main menu "Plugins / Runner":

  * Build -- Run main command from the build-config.
  * Build with... -- Show menu to choose from all variants in the build-config,
        and run chosen item.
  * Choose build config... -- Associate some build-config with current lexer.
        For documents without lexer the file extension is used.
  * Next/Previous output -- Switch the CudaText Output panel between recent logs
        (for ex, if you run build-system 3 times, you have 3 recent logs). 
  * Cancel build -- Stop the currently running external process.


Config file
-----------

Plugin has the config file, which is accessible via main menu:
"Options / Settings-plugins / Runner". Options:

  * "max_logs" -- Maximal count of recent logs, which are remembered.
  * "lexmap" -- Lexer to build-system associations, edited through "Choose build config..." dialog.
  * "extmap" -- File-mask (Unix shell-style wildcards) to build-system association, 
          edited through "Choose build config..." dialog.

It is possible to bind hotkey to a specific build command. This can be done by
adding subcommand description to the "subcommands" category in the plugin's config. 
Format of subcommand:
  "<caption>": "<build system>|<command name>"

  * <caption> -- Custom name of new command to be displayed in Command Pallete.
  * <build system> -- Filename of build system (with or without extension).
  * <command name> -- Name of command in build system, as listed in the "Build with..." dialog.

For example:
  ...
  "subcommands": {
    "Quick Py lint": "python_stuff|lint"
  },
  ...
This will add command "Quick Py lint" to Command Palette, that will run "lint" command from 
"python_stuff.sublime-build" build-system.


Log lines
---------

Additional information can be added to the build logs, format of which can be customized via 
config options "build_log_start_info" and "build_log_finish_info".
Many macros is supported here:

  * values from the executed command - www.sublimetext.com/docs/3/build_systems.html#exec_options
  * document variables - http://www.sublimetext.com/docs/3/build_systems.html#variable-packages
  * build process information:
  
    * $build_name -- Name of build-system.
    * $start_time -- Date/time when process was executed.
    * $duration -- Duration of process running.
    * $return_code -- Return-code of the process.


About
-----

Author: Shovel, https://github.com/halfbrained/
License: MIT
