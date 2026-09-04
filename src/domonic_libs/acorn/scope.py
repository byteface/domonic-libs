# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/scope.js.
"""Lexical-scope bookkeeping for duplicate-declaration detection."""

from __future__ import annotations

from .scopeflags import (
    BIND_FUNCTION,
    BIND_LEXICAL,
    BIND_SIMPLE_CATCH,
    SCOPE_ARROW,
    SCOPE_CLASS_FIELD_INIT,
    SCOPE_CLASS_STATIC_BLOCK,
    SCOPE_FUNCTION,
    SCOPE_SIMPLE_CATCH,
    SCOPE_TOP,
    SCOPE_VAR,
)


class Scope:
    def __init__(self, flags):
        self.flags = flags
        self.var = []
        self.lexical = []
        self.functions = []


class ScopeMixin:
    def enterScope(self, flags):
        self.scopeStack.append(Scope(flags))

    def exitScope(self):
        self.scopeStack.pop()

    def treatFunctionsAsVarInScope(self, scope):
        return bool((scope.flags & SCOPE_FUNCTION) or (not self.inModule and (scope.flags & SCOPE_TOP)))

    def declareName(self, name, bindingType, pos):
        redeclared = False
        if bindingType == BIND_LEXICAL:
            scope = self.currentScope()
            redeclared = name in scope.lexical or name in scope.functions or name in scope.var
            scope.lexical.append(name)
            if self.inModule and (scope.flags & SCOPE_TOP):
                self.undefinedExports.pop(name, None)
        elif bindingType == BIND_SIMPLE_CATCH:
            self.currentScope().lexical.append(name)
        elif bindingType == BIND_FUNCTION:
            scope = self.currentScope()
            if self.treatFunctionsAsVar:
                redeclared = name in scope.lexical
            else:
                redeclared = name in scope.lexical or name in scope.var
            scope.functions.append(name)
        else:
            for i in range(len(self.scopeStack) - 1, -1, -1):
                scope = self.scopeStack[i]
                if (name in scope.lexical and not ((scope.flags & SCOPE_SIMPLE_CATCH) and scope.lexical[0] == name)) \
                        or (not self.treatFunctionsAsVarInScope(scope) and name in scope.functions):
                    redeclared = True
                    break
                scope.var.append(name)
                if self.inModule and (scope.flags & SCOPE_TOP):
                    self.undefinedExports.pop(name, None)
                if scope.flags & SCOPE_VAR:
                    break
        if redeclared:
            self.raiseRecoverable(pos, f"Identifier '{name}' has already been declared")

    def checkLocalExport(self, id):
        if id.name not in self.scopeStack[0].lexical and id.name not in self.scopeStack[0].var:
            self.undefinedExports[id.name] = id

    def currentScope(self):
        return self.scopeStack[-1]

    def currentVarScope(self):
        i = len(self.scopeStack) - 1
        while True:
            scope = self.scopeStack[i]
            if scope.flags & (SCOPE_VAR | SCOPE_CLASS_FIELD_INIT | SCOPE_CLASS_STATIC_BLOCK):
                return scope
            i -= 1

    def currentThisScope(self):
        i = len(self.scopeStack) - 1
        while True:
            scope = self.scopeStack[i]
            if (scope.flags & (SCOPE_VAR | SCOPE_CLASS_FIELD_INIT | SCOPE_CLASS_STATIC_BLOCK)) \
                    and not (scope.flags & SCOPE_ARROW):
                return scope
            i -= 1
