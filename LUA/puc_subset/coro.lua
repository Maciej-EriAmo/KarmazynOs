-- puc_subset: coroutine
local co = coroutine.create(function()
  coroutine.yield(10)
  return 20
end)
local ok, v = coroutine.resume(co)
assert(ok and v == 10)
ok, v = coroutine.resume(co)
assert(ok and v == 20)
assert(coroutine.status(co) == "dead")
assert(coroutine.isyieldable() == false)
return "ok"
