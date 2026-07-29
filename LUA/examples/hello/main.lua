-- examples/hello — wieloplikowy program na host CLI
local util = require "util"
local greeter = require "lib.greeter"

print(util.banner())
print(greeter.hello("Karmazyn"))
return greeter.hello("world")
