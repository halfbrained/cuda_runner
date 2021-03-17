Plugin for CudaText.

Adds commands to build/compile files/projects. Supports configs in Sublime Text format - .sublime-build

Commands are in the main menu: "Plugins > Runner":
	* Build - main command from the build-config
	* Build with... - choose from all build commands in the build-config
	* Choose build config... - associate build-config with current lexer. For files without lexer extension is used.
	* Next/Previous output - allows to switch between build logs. 
	* Cancel build - cancels build process

Max number of saved logs can be changed in config, accessible via menu command: "Options > Settings-plugins > Config",
options is "max_logs".

Authors
-------
  Shovel, https://github.com/halfbrained/
License: MIT
