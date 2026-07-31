-- puc_subset: arytmetyka
local function eq(a, b, msg)
  if a ~= b then error((msg or "eq") .. ": " .. tostring(a) .. " ~= " .. tostring(b)) end
end
eq(1 + 2 * 3, 7, "prec")
eq(2 ^ 3, 8.0, "pow")
eq(7 // 2, 3, "idiv")
eq(10 % 3, 1, "mod")
eq(-7 // 2, -4, "idiv.neg")
return "ok"
