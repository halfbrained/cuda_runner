Plugin for CudaText.
Adds support for build-systems from Sublime Text 3. It runs external tools, using
configurations stored in ST3's build-systems, files with .sublime-build extension.
Only those build-systems are supported that do not require additional Python code
(Python code in ST3 plugin which contained that build-system).

Build-system files must be copied to [CudaText]/data/buildsystems folder.
Sometimes ST3 packages with build-systems include also binaries (.exe files).
These binaries must be copied to [CudaText]/data/buildsystems/tools folder.

Plugin gives commands in the main menu "Plugins / Runner":

  * Build -- Run main command from the build-config.
  * Build with... -- Show menu to choose from all variants in the build-config,
	    and run chosen item.
  * Choose build config... -- Associate some build-config with current lexer.
	    For documents without lexer the file extension is used.
  * Next/Previous output -- Switch the CudaText Output panel between recent logs
	    (for ex, if you run build-system 3 times, you have 3 recent logs). 
  * Cancel build -- Stop the currently running external process.


Plugin has the config file, which is accessible via main menu:
"Options / Settings-plugins / Runner". Options:

  * "max_logs" -- Maximal count of recent logs, which are remembered.


It is possible to bind hotkey to a specific build command. This can be done by
adding subcommand description to the "subcommands" category in the config. 
Format of subcommand:
  "<caption>": "<build system>|<command name>"

  * <caption> - custom name of new command to be displayed in Command Pallete.
  * <build system> - filename of build system (with or without extension)
  * <command name> - name of command in build config, as listed in the "Build with..." dialog.


Additional information can be added to the build logs, format of which can be customized via 
config options "build_log_start_info" and "build_log_finish_info". A number of macros is supported here:
  * values from the executed command - www.sublimetext.com/docs/3/build_systems.html#exec_options
  * document variables - http://www.sublimetext.com/docs/3/build_systems.html#variable-packages
  * build process information:
  
	* $build_name -- Name of build-system.
  	* $start_time -- Date/time when process was executed.
	* $duration -- Duration of process running.
  	* $return_code -- Return-code of the process.


Author: Shovel, https://github.com/halfbrained/
License: MIT