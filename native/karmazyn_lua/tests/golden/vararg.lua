local function f(...)
    return select("#", ...)
end
return f(1, 2, 3)
