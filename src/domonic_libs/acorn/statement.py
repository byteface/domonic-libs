# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/statement.js.
"""Statement, declaration, class, and module (import/export) parsing."""

from __future__ import annotations

from .identifier import isIdentifierChar, isIdentifierStart, keywordRelationalOperator
from .parseutil import DestructuringErrors
from .scopeflags import (
    BIND_FUNCTION,
    BIND_LEXICAL,
    BIND_SIMPLE_CATCH,
    BIND_VAR,
    SCOPE_CLASS_FIELD_INIT,
    SCOPE_CLASS_STATIC_BLOCK,
    SCOPE_SIMPLE_CATCH,
    SCOPE_SUPER,
    SCOPE_SWITCH,
    functionFlags,
)
from .tokentype import tt
from .util import hasOwn, loneSurrogate
from .whitespace import lineBreak, skipWhiteSpace

_loopLabel = {"kind": "loop"}
_switchLabel = {"kind": "switch"}
_EMPTY = []

FUNC_STATEMENT = 1
FUNC_HANGING_STATEMENT = 2
FUNC_NULLABLE_ID = 4


def _checkKeyName(node, name):
    key = node.key
    return not node.computed and (
        (key.type == "Identifier" and key.name == name)
        or (key.type == "Literal" and key.value == name)
    )


def _isPrivateNameConflicted(privateNameMap, element):
    name = element.key.name
    curr = privateNameMap.get(name)
    next_ = "true"
    if element.type == "MethodDefinition" and (element.kind == "get" or element.kind == "set"):
        next_ = ("s" if element.static else "i") + element.kind
    if (curr == "iget" and next_ == "iset") or (curr == "iset" and next_ == "iget") \
            or (curr == "sget" and next_ == "sset") or (curr == "sset" and next_ == "sget"):
        privateNameMap[name] = "true"
        return False
    elif not curr:
        privateNameMap[name] = next_
        return False
    return True


class StatementMixin:
    def parseTopLevel(self, node):
        exports = {}
        if not getattr(node, "body", None):
            node.body = []
        while self.type is not tt.eof:
            stmt = self.parseStatement(None, True, exports)
            node.body.append(stmt)
        if self.inModule:
            for name in list(self.undefinedExports):
                self.raiseRecoverable(self.undefinedExports[name].start, f"Export '{name}' is not defined")
        self.adaptDirectivePrologue(node.body)
        self.next()
        node.__dict__["sourceType"] = "script" if self.options["sourceType"] == "commonjs" else self.options["sourceType"]
        return self.finishNode(node, "Program")

    def isLet(self, context=None):
        if self.options["ecmaVersion"] < 6 or not self.isContextual("let"):
            return False
        skipWhiteSpace.lastIndex = self.pos
        skip = skipWhiteSpace.exec(self.input)
        nxt = self.pos + len(skip[0] if skip else "")
        nextCh = self.fullCharCodeAt(nxt)
        if nextCh == 91 or nextCh == 92:
            return True
        if context:
            return False
        if nextCh == 123:
            return True
        if isIdentifierStart(nextCh):
            start = nxt
            while True:
                nxt += 1 if nextCh <= 0xFFFF else 2
                nextCh = self.fullCharCodeAt(nxt)
                if not isIdentifierChar(nextCh):
                    break
            if nextCh == 92:
                return True
            ident = str(self.input.slice(start, nxt))
            if not bool(keywordRelationalOperator.test(ident)):
                return True
        return False

    def isAsyncFunction(self):
        if self.options["ecmaVersion"] < 8 or not self.isContextual("async"):
            return False
        skipWhiteSpace.lastIndex = self.pos
        skip = skipWhiteSpace.exec(self.input)
        nxt = self.pos + len(skip[0] if skip else "")
        if bool(lineBreak.test(self.input.slice(self.pos, nxt))):
            return False
        if str(self.input.slice(nxt, nxt + 8)) != "function":
            return False
        if nxt + 8 == self.input.length:
            return True
        after = self.fullCharCodeAt(nxt + 8)
        return not (isIdentifierChar(after) or after == 92)

    def isUsingKeyword(self, isAwaitUsing, isFor):
        if self.options["ecmaVersion"] < 17 or not self.isContextual("await" if isAwaitUsing else "using"):
            return False
        skipWhiteSpace.lastIndex = self.pos
        skip = skipWhiteSpace.exec(self.input)
        nxt = self.pos + len(skip[0] if skip else "")
        if bool(lineBreak.test(self.input.slice(self.pos, nxt))):
            return False
        if isAwaitUsing:
            usingEndPos = nxt + 5
            if (str(self.input.slice(nxt, usingEndPos)) != "using" or usingEndPos == self.input.length
                    or isIdentifierChar(self.fullCharCodeAt(usingEndPos)) or self.fullCharCodeAt(usingEndPos) == 92):
                return False
            skipWhiteSpace.lastIndex = usingEndPos
            skipAfterUsing = skipWhiteSpace.exec(self.input)
            nxt = usingEndPos + len(skipAfterUsing[0] if skipAfterUsing else "")
            if skipAfterUsing and bool(lineBreak.test(self.input.slice(usingEndPos, nxt))):
                return False
        ch = self.fullCharCodeAt(nxt)
        if not isIdentifierStart(ch) and ch != 92:
            return False
        idStart = nxt
        while True:
            nxt += 1 if ch <= 0xFFFF else 2
            ch = self.fullCharCodeAt(nxt)
            if not isIdentifierChar(ch):
                break
        if ch == 92:
            return True
        idn = str(self.input.slice(idStart, nxt))
        if bool(keywordRelationalOperator.test(idn)):
            return False
        if isFor and not isAwaitUsing and idn == "of":
            skipWhiteSpace.lastIndex = nxt
            skipAfterOf = skipWhiteSpace.exec(self.input)
            nxt = nxt + len(skipAfterOf[0] if skipAfterOf else "")
            if self.input.charCodeAt(nxt) != 61:
                return False
            ch2 = self.input.charCodeAt(nxt + 1)
            if ch2 == 61 or ch2 == 62:
                return False
        return True

    def isAwaitUsing(self, isFor):
        return self.isUsingKeyword(True, isFor)

    def isUsing(self, isFor):
        return self.isUsingKeyword(False, isFor)

    def parseStatement(self, context, topLevel=False, exports=None):
        starttype = self.type
        node = self.startNode()
        kind = None
        if self.isLet(context):
            starttype = tt._var
            kind = "let"

        if starttype is tt._break or starttype is tt._continue:
            return self.parseBreakContinueStatement(node, starttype.keyword)
        if starttype is tt._debugger:
            return self.parseDebuggerStatement(node)
        if starttype is tt._do:
            return self.parseDoStatement(node)
        if starttype is tt._for:
            return self.parseForStatement(node)
        if starttype is tt._function:
            if (context and (self.strict or (context != "if" and context != "label"))) and self.options["ecmaVersion"] >= 6:
                self.unexpected()
            return self.parseFunctionStatement(node, False, not context)
        if starttype is tt._class:
            if context:
                self.unexpected()
            return self.parseClass(node, True)
        if starttype is tt._if:
            return self.parseIfStatement(node)
        if starttype is tt._return:
            return self.parseReturnStatement(node)
        if starttype is tt._switch:
            return self.parseSwitchStatement(node)
        if starttype is tt._throw:
            return self.parseThrowStatement(node)
        if starttype is tt._try:
            return self.parseTryStatement(node)
        if starttype is tt._const or starttype is tt._var:
            kind = kind or self.value
            if context and kind != "var":
                self.unexpected()
            return self.parseVarStatement(node, kind)
        if starttype is tt._while:
            return self.parseWhileStatement(node)
        if starttype is tt._with:
            return self.parseWithStatement(node)
        if starttype is tt.braceL:
            return self.parseBlock(True, node)
        if starttype is tt.semi:
            return self.parseEmptyStatement(node)
        if starttype is tt._export or starttype is tt._import:
            if self.options["ecmaVersion"] > 10 and starttype is tt._import:
                skipWhiteSpace.lastIndex = self.pos
                skip = skipWhiteSpace.exec(self.input)
                nxt = self.pos + len(skip[0] if skip else "")
                nextCh = self.input.charCodeAt(nxt)
                if nextCh == 40 or nextCh == 46:
                    return self.parseExpressionStatement(node, self.parseExpression())
            if not self.options["allowImportExportEverywhere"]:
                if not topLevel:
                    self.raise_(self.start, "'import' and 'export' may only appear at the top level")
                if not self.inModule:
                    self.raise_(self.start, "'import' and 'export' may appear only with 'sourceType: module'")
            return self.parseImport(node) if starttype is tt._import else self.parseExport(node, exports)

        if self.isAsyncFunction():
            if context:
                self.unexpected()
            self.next()
            return self.parseFunctionStatement(node, True, not context)

        usingKind = "await using" if self.isAwaitUsing(False) else ("using" if self.isUsing(False) else None)
        if usingKind:
            if not self.allowUsing:
                self.raise_(self.start, "Using declaration cannot appear in the top level when source type is `script` or in the bare case statement")
            if context:
                self.raise_(self.start, "Using declaration is not allowed in single-statement positions")
            if usingKind == "await using":
                if not self.canAwait:
                    self.raise_(self.start, "Await using cannot appear outside of async function")
                self.next()
            self.next()
            self.parseVar(node, False, usingKind)
            self.semicolon()
            return self.finishNode(node, "VariableDeclaration")

        maybeName = self.value
        expr = self.parseExpression()
        if starttype is tt.name and expr.type == "Identifier" and self.eat(tt.colon):
            return self.parseLabeledStatement(node, maybeName, expr, context)
        return self.parseExpressionStatement(node, expr)

    def parseBreakContinueStatement(self, node, keyword):
        isBreak = keyword == "break"
        self.next()
        if self.eat(tt.semi) or self.insertSemicolon():
            node.label = None
        elif self.type is not tt.name:
            self.unexpected()
        else:
            node.label = self.parseIdent()
            self.semicolon()
        i = 0
        while i < len(self.labels):
            lab = self.labels[i]
            if node.label is None or lab.get("name") == node.label.name:
                if lab.get("kind") is not None and (isBreak or lab["kind"] == "loop"):
                    break
                if node.label and isBreak:
                    break
            i += 1
        if i == len(self.labels):
            self.raise_(node.start, "Unsyntactic " + keyword)
        return self.finishNode(node, "BreakStatement" if isBreak else "ContinueStatement")

    def parseDebuggerStatement(self, node):
        self.next()
        self.semicolon()
        return self.finishNode(node, "DebuggerStatement")

    def parseDoStatement(self, node):
        self.next()
        self.labels.append(_loopLabel)
        node.body = self.parseStatement("do")
        self.labels.pop()
        self.expect(tt._while)
        node.test = self.parseParenExpression()
        if self.options["ecmaVersion"] >= 6:
            self.eat(tt.semi)
        else:
            self.semicolon()
        return self.finishNode(node, "DoWhileStatement")

    def parseForStatement(self, node):
        self.next()
        awaitAt = self.lastTokStart if (self.options["ecmaVersion"] >= 9 and self.canAwait and self.eatContextual("await")) else -1
        self.labels.append(_loopLabel)
        self.enterScope(0)
        self.expect(tt.parenL)
        if self.type is tt.semi:
            if awaitAt > -1:
                self.unexpected(awaitAt)
            return self.parseFor(node, None)
        isLet = self.isLet()
        if self.type is tt._var or self.type is tt._const or isLet:
            init = self.startNode()
            kind = "let" if isLet else self.value
            self.next()
            self.parseVar(init, True, kind)
            self.finishNode(init, "VariableDeclaration")
            return self.parseForAfterInit(node, init, awaitAt)
        startsWithLet = self.isContextual("let")
        isForOf = False
        usingKind = "using" if self.isUsing(True) else ("await using" if self.isAwaitUsing(True) else None)
        if usingKind:
            init = self.startNode()
            self.next()
            if usingKind == "await using":
                if not self.canAwait:
                    self.raise_(self.start, "Await using cannot appear outside of async function")
                self.next()
            self.parseVar(init, True, usingKind)
            self.finishNode(init, "VariableDeclaration")
            return self.parseForAfterInit(node, init, awaitAt)
        containsEsc = self.containsEsc
        refDestructuringErrors = DestructuringErrors()
        initPos = self.start
        init = (self.parseExprSubscripts(refDestructuringErrors, "await") if awaitAt > -1
                else self.parseExpression(True, refDestructuringErrors))
        isForOf = self.options["ecmaVersion"] >= 6 and self.isContextual("of")
        if self.type is tt._in or isForOf:
            if awaitAt > -1:
                if self.type is tt._in:
                    self.unexpected(awaitAt)
                node.__dict__["await"] = True
            elif isForOf and self.options["ecmaVersion"] >= 8:
                if init.start == initPos and not containsEsc and init.type == "Identifier" and init.name == "async":
                    self.unexpected()
                elif self.options["ecmaVersion"] >= 9:
                    node.__dict__["await"] = False
            if startsWithLet and isForOf:
                self.raise_(init.start, "The left-hand side of a for-of loop may not start with 'let'.")
            self.toAssignable(init, False, refDestructuringErrors)
            self.checkLValPattern(init)
            return self.parseForIn(node, init)
        else:
            self.checkExpressionErrors(refDestructuringErrors, True)
        if awaitAt > -1:
            self.unexpected(awaitAt)
        return self.parseFor(node, init)

    def parseForAfterInit(self, node, init, awaitAt):
        if ((self.type is tt._in or (self.options["ecmaVersion"] >= 6 and self.isContextual("of")))
                and len(init.declarations) == 1):
            if self.type is tt._in:
                if (init.kind in ("using", "await using")) and not getattr(init.declarations[0], "init", None):
                    self.raise_(self.start, "Using declaration is not allowed in for-in loops")
                if self.options["ecmaVersion"] >= 9 and awaitAt > -1:
                    self.unexpected(awaitAt)
            elif self.options["ecmaVersion"] >= 9:
                node.__dict__["await"] = awaitAt > -1
            return self.parseForIn(node, init)
        if awaitAt > -1:
            self.unexpected(awaitAt)
        return self.parseFor(node, init)

    def parseFunctionStatement(self, node, isAsync, declarationPosition):
        self.next()
        return self.parseFunction(node, FUNC_STATEMENT | (0 if declarationPosition else FUNC_HANGING_STATEMENT), False, isAsync)

    def parseIfStatement(self, node):
        self.next()
        node.test = self.parseParenExpression()
        node.consequent = self.parseStatement("if")
        node.alternate = self.parseStatement("if") if self.eat(tt._else) else None
        return self.finishNode(node, "IfStatement")

    def parseReturnStatement(self, node):
        if not self.allowReturn:
            self.raise_(self.start, "'return' outside of function")
        self.next()
        if self.eat(tt.semi) or self.insertSemicolon():
            node.argument = None
        else:
            node.argument = self.parseExpression()
            self.semicolon()
        return self.finishNode(node, "ReturnStatement")

    def parseSwitchStatement(self, node):
        self.next()
        node.discriminant = self.parseParenExpression()
        node.cases = []
        self.expect(tt.braceL)
        self.labels.append(_switchLabel)
        self.enterScope(SCOPE_SWITCH)
        cur = None
        sawDefault = False
        while self.type is not tt.braceR:
            if self.type is tt._case or self.type is tt._default:
                isCase = self.type is tt._case
                if cur:
                    self.finishNode(cur, "SwitchCase")
                cur = self.startNode()
                node.cases.append(cur)
                cur.consequent = []
                self.next()
                if isCase:
                    cur.test = self.parseExpression()
                else:
                    if sawDefault:
                        self.raiseRecoverable(self.lastTokStart, "Multiple default clauses")
                    sawDefault = True
                    cur.test = None
                self.expect(tt.colon)
            else:
                if not cur:
                    self.unexpected()
                cur.consequent.append(self.parseStatement(None))
        self.exitScope()
        if cur:
            self.finishNode(cur, "SwitchCase")
        self.next()
        self.labels.pop()
        return self.finishNode(node, "SwitchStatement")

    def parseThrowStatement(self, node):
        self.next()
        if bool(lineBreak.test(self.input.slice(self.lastTokEnd, self.start))):
            self.raise_(self.lastTokEnd, "Illegal newline after throw")
        node.argument = self.parseExpression()
        self.semicolon()
        return self.finishNode(node, "ThrowStatement")

    def parseCatchClauseParam(self):
        param = self.parseBindingAtom()
        simple = param.type == "Identifier"
        self.enterScope(SCOPE_SIMPLE_CATCH if simple else 0)
        self.checkLValPattern(param, BIND_SIMPLE_CATCH if simple else BIND_LEXICAL)
        self.expect(tt.parenR)
        return param

    def parseTryStatement(self, node):
        self.next()
        node.block = self.parseBlock()
        node.handler = None
        if self.type is tt._catch:
            clause = self.startNode()
            self.next()
            if self.eat(tt.parenL):
                clause.param = self.parseCatchClauseParam()
            else:
                if self.options["ecmaVersion"] < 10:
                    self.unexpected()
                clause.param = None
                self.enterScope(0)
            clause.body = self.parseBlock(False)
            self.exitScope()
            node.handler = self.finishNode(clause, "CatchClause")
        node.finalizer = self.parseBlock() if self.eat(tt._finally) else None
        if not node.handler and not node.finalizer:
            self.raise_(node.start, "Missing catch or finally clause")
        return self.finishNode(node, "TryStatement")

    def parseVarStatement(self, node, kind, allowMissingInitializer=False):
        self.next()
        self.parseVar(node, False, kind, allowMissingInitializer)
        self.semicolon()
        return self.finishNode(node, "VariableDeclaration")

    def parseWhileStatement(self, node):
        self.next()
        node.test = self.parseParenExpression()
        self.labels.append(_loopLabel)
        node.body = self.parseStatement("while")
        self.labels.pop()
        return self.finishNode(node, "WhileStatement")

    def parseWithStatement(self, node):
        if self.strict:
            self.raise_(self.start, "'with' in strict mode")
        self.next()
        node.object = self.parseParenExpression()
        node.body = self.parseStatement("with")
        return self.finishNode(node, "WithStatement")

    def parseEmptyStatement(self, node):
        self.next()
        return self.finishNode(node, "EmptyStatement")

    def parseLabeledStatement(self, node, maybeName, expr, context):
        for label in self.labels:
            # an unlabeled loop pushes a nameless sentinel (`_loopLabel`, just
            # `{"kind": "loop"}`, to track break/continue validity) -- a real
            # label always has a name, so `.get` (not `[...]`) is what makes
            # a labeled statement *inside* a plain loop not crash the parser.
            if label.get("name") == maybeName:
                self.raise_(expr.start, "Label '" + maybeName + "' is already declared")
        kind = "loop" if self.type.isLoop else ("switch" if self.type is tt._switch else None)
        for i in range(len(self.labels) - 1, -1, -1):
            label = self.labels[i]
            if label.get("statementStart") == node.start:
                label["statementStart"] = self.start
                label["kind"] = kind
            else:
                break
        self.labels.append({"name": maybeName, "kind": kind, "statementStart": self.start})
        inner = (context if context and "label" in context else (context + "label") if context else "label")
        node.body = self.parseStatement(inner)
        self.labels.pop()
        node.label = expr
        return self.finishNode(node, "LabeledStatement")

    def parseExpressionStatement(self, node, expr):
        node.expression = expr
        self.semicolon()
        return self.finishNode(node, "ExpressionStatement")

    def parseBlock(self, createNewLexicalScope=True, node=None, exitStrict=False):
        if node is None:
            node = self.startNode()
        node.body = []
        self.expect(tt.braceL)
        if createNewLexicalScope:
            self.enterScope(0)
        while self.type is not tt.braceR:
            stmt = self.parseStatement(None)
            node.body.append(stmt)
        if exitStrict:
            self.strict = False
        self.next()
        if createNewLexicalScope:
            self.exitScope()
        return self.finishNode(node, "BlockStatement")

    def parseFor(self, node, init):
        node.init = init
        self.expect(tt.semi)
        node.test = None if self.type is tt.semi else self.parseExpression()
        self.expect(tt.semi)
        node.update = None if self.type is tt.parenR else self.parseExpression()
        self.expect(tt.parenR)
        node.body = self.parseStatement("for")
        self.exitScope()
        self.labels.pop()
        return self.finishNode(node, "ForStatement")

    def parseForIn(self, node, init):
        isForIn = self.type is tt._in
        self.next()
        if (init.type == "VariableDeclaration" and getattr(init.declarations[0], "init", None) is not None
                and (not isForIn or self.options["ecmaVersion"] < 8 or self.strict or init.kind != "var"
                     or init.declarations[0].id.type != "Identifier")):
            self.raise_(init.start, f"{'for-in' if isForIn else 'for-of'} loop variable declaration may not have an initializer")
        node.left = init
        node.right = self.parseExpression() if isForIn else self.parseMaybeAssign()
        self.expect(tt.parenR)
        node.body = self.parseStatement("for")
        self.exitScope()
        self.labels.pop()
        return self.finishNode(node, "ForInStatement" if isForIn else "ForOfStatement")

    def parseVar(self, node, isFor, kind, allowMissingInitializer=False):
        node.declarations = []
        node.kind = kind
        while True:
            decl = self.startNode()
            self.parseVarId(decl, kind)
            if self.eat(tt.eq):
                decl.init = self.parseMaybeAssign(isFor)
            elif (not allowMissingInitializer and kind == "const"
                  and not (self.type is tt._in or (self.options["ecmaVersion"] >= 6 and self.isContextual("of")))):
                self.unexpected()
            elif (not allowMissingInitializer and kind in ("using", "await using")
                  and self.options["ecmaVersion"] >= 17 and self.type is not tt._in and not self.isContextual("of")):
                self.raise_(self.lastTokEnd, f"Missing initializer in {kind} declaration")
            elif (not allowMissingInitializer and decl.id.type != "Identifier"
                  and not (isFor and (self.type is tt._in or self.isContextual("of")))):
                self.raise_(self.lastTokEnd, "Complex binding patterns require an initialization value")
            else:
                decl.init = None
            node.declarations.append(self.finishNode(decl, "VariableDeclarator"))
            if not self.eat(tt.comma):
                break
        return node

    def parseVarId(self, decl, kind):
        decl.id = self.parseIdent() if kind in ("using", "await using") else self.parseBindingAtom()
        self.checkLValPattern(decl.id, BIND_VAR if kind == "var" else BIND_LEXICAL, None)

    def parseFunction(self, node, statement, allowExpressionBody=False, isAsync=False, forInit=False):
        self.initFunction(node)
        if self.options["ecmaVersion"] >= 9 or (self.options["ecmaVersion"] >= 6 and not isAsync):
            if self.type is tt.star and (statement & FUNC_HANGING_STATEMENT):
                self.unexpected()
            node.generator = self.eat(tt.star)
        if self.options["ecmaVersion"] >= 8:
            node.__dict__["async"] = bool(isAsync)
        if statement & FUNC_STATEMENT:
            node.id = None if ((statement & FUNC_NULLABLE_ID) and self.type is not tt.name) else self.parseIdent()
            if node.id and not (statement & FUNC_HANGING_STATEMENT):
                bind = (BIND_VAR if self.treatFunctionsAsVar else BIND_LEXICAL) \
                    if (self.strict or node.generator or getattr(node, "async", False)) else BIND_FUNCTION
                self.checkLValSimple(node.id, bind)
        oldYieldPos, oldAwaitPos, oldAwaitIdentPos = self.yieldPos, self.awaitPos, self.awaitIdentPos
        self.yieldPos = self.awaitPos = self.awaitIdentPos = 0
        self.enterScope(functionFlags(getattr(node, "async", False), node.generator))
        if not (statement & FUNC_STATEMENT):
            node.id = self.parseIdent() if self.type is tt.name else None
        self.parseFunctionParams(node)
        self.parseFunctionBody(node, allowExpressionBody, False, forInit)
        self.yieldPos, self.awaitPos, self.awaitIdentPos = oldYieldPos, oldAwaitPos, oldAwaitIdentPos
        return self.finishNode(node, "FunctionDeclaration" if (statement & FUNC_STATEMENT) else "FunctionExpression")

    def parseFunctionParams(self, node):
        self.expect(tt.parenL)
        node.params = self.parseBindingList(tt.parenR, False, self.options["ecmaVersion"] >= 8)
        self.checkYieldAwaitInDefaultParams()

    def parseClass(self, node, isStatement):
        self.next()
        oldStrict = self.strict
        self.strict = True
        self.parseClassId(node, isStatement)
        self.parseClassSuper(node)
        privateNameMap = self.enterClassBody()
        classBody = self.startNode()
        hadConstructor = False
        classBody.body = []
        self.expect(tt.braceL)
        while self.type is not tt.braceR:
            element = self.parseClassElement(node.superClass is not None)
            if element:
                classBody.body.append(element)
                if element.type == "MethodDefinition" and element.kind == "constructor":
                    if hadConstructor:
                        self.raiseRecoverable(element.start, "Duplicate constructor in the same class")
                    hadConstructor = True
                elif getattr(element, "key", None) and element.key.type == "PrivateIdentifier" \
                        and _isPrivateNameConflicted(privateNameMap, element):
                    self.raiseRecoverable(element.key.start, f"Identifier '#{element.key.name}' has already been declared")
        self.strict = oldStrict
        self.next()
        node.body = self.finishNode(classBody, "ClassBody")
        self.exitClassBody()
        return self.finishNode(node, "ClassDeclaration" if isStatement else "ClassExpression")

    def parseClassElement(self, constructorAllowsSuper):
        if self.eat(tt.semi):
            return None
        ecmaVersion = self.options["ecmaVersion"]
        node = self.startNode()
        keyName = ""
        isGenerator = False
        isAsync = False
        kind = "method"
        isStatic = False
        if self.eatContextual("static"):
            if ecmaVersion >= 13 and self.eat(tt.braceL):
                self.parseClassStaticBlock(node)
                return node
            if self.isClassElementNameStart() or self.type is tt.star:
                isStatic = True
            else:
                keyName = "static"
        node.static = isStatic
        if not keyName and ecmaVersion >= 8 and self.eatContextual("async"):
            if (self.isClassElementNameStart() or self.type is tt.star) and not self.canInsertSemicolon():
                isAsync = True
            else:
                keyName = "async"
        if not keyName and (ecmaVersion >= 9 or not isAsync) and self.eat(tt.star):
            isGenerator = True
        if not keyName and not isAsync and not isGenerator:
            lastValue = self.value
            if self.eatContextual("get") or self.eatContextual("set"):
                if self.isClassElementNameStart():
                    kind = lastValue
                else:
                    keyName = lastValue
        if keyName:
            node.computed = False
            node.key = self.startNodeAt(self.lastTokStart, self.lastTokStartLoc)
            node.key.name = keyName
            self.finishNode(node.key, "Identifier")
        else:
            self.parseClassElementName(node)
        if ecmaVersion < 13 or self.type is tt.parenL or kind != "method" or isGenerator or isAsync:
            isConstructor = not node.static and _checkKeyName(node, "constructor")
            allowsDirectSuper = isConstructor and constructorAllowsSuper
            if isConstructor and kind != "method":
                self.raise_(node.key.start, "Constructor can't have get/set modifier")
            node.kind = "constructor" if isConstructor else kind
            self.parseClassMethod(node, isGenerator, isAsync, allowsDirectSuper)
        else:
            self.parseClassField(node)
        return node

    def isClassElementNameStart(self):
        return (self.type is tt.name or self.type is tt.privateId or self.type is tt.num
                or self.type is tt.string or self.type is tt.bracketL or bool(self.type.keyword))

    def parseClassElementName(self, element):
        if self.type is tt.privateId:
            if self.value == "constructor":
                self.raise_(self.start, "Classes can't have an element named '#constructor'")
            element.computed = False
            element.key = self.parsePrivateIdent()
        else:
            self.parsePropertyName(element)

    def parseClassMethod(self, method, isGenerator, isAsync, allowsDirectSuper):
        key = method.key
        if method.kind == "constructor":
            if isGenerator:
                self.raise_(key.start, "Constructor can't be a generator")
            if isAsync:
                self.raise_(key.start, "Constructor can't be an async method")
        elif method.static and _checkKeyName(method, "prototype"):
            self.raise_(key.start, "Classes may not have a static property named prototype")
        value = method.value = self.parseMethod(isGenerator, isAsync, allowsDirectSuper)
        if method.kind == "get" and len(value.params) != 0:
            self.raiseRecoverable(value.start, "getter should have no params")
        if method.kind == "set" and len(value.params) != 1:
            self.raiseRecoverable(value.start, "setter should have exactly one param")
        if method.kind == "set" and value.params[0].type == "RestElement":
            self.raiseRecoverable(value.params[0].start, "Setter cannot use rest params")
        return self.finishNode(method, "MethodDefinition")

    def parseClassField(self, field):
        if _checkKeyName(field, "constructor"):
            self.raise_(field.key.start, "Classes can't have a field named 'constructor'")
        elif field.static and _checkKeyName(field, "prototype"):
            self.raise_(field.key.start, "Classes can't have a static field named 'prototype'")
        if self.eat(tt.eq):
            self.enterScope(SCOPE_CLASS_FIELD_INIT | SCOPE_SUPER)
            field.value = self.parseMaybeAssign()
            self.exitScope()
        else:
            field.value = None
        self.semicolon()
        return self.finishNode(field, "PropertyDefinition")

    def parseClassStaticBlock(self, node):
        node.body = []
        oldLabels = self.labels
        self.labels = []
        self.enterScope(SCOPE_CLASS_STATIC_BLOCK | SCOPE_SUPER)
        while self.type is not tt.braceR:
            node.body.append(self.parseStatement(None))
        self.next()
        self.exitScope()
        self.labels = oldLabels
        return self.finishNode(node, "StaticBlock")

    def parseClassId(self, node, isStatement):
        if self.type is tt.name:
            node.id = self.parseIdent()
            if isStatement:
                self.checkLValSimple(node.id, BIND_LEXICAL, None)
        else:
            if isStatement is True:
                self.unexpected()
            node.id = None

    def parseClassSuper(self, node):
        node.superClass = self.parseExprSubscripts(None, False) if self.eat(tt._extends) else None

    def enterClassBody(self):
        element = {"declared": {}, "used": []}
        self.privateNameStack.append(element)
        return element["declared"]

    def exitClassBody(self):
        popped = self.privateNameStack.pop()
        declared, used = popped["declared"], popped["used"]
        if not self.options["checkPrivateFields"]:
            return
        length = len(self.privateNameStack)
        parent = None if length == 0 else self.privateNameStack[length - 1]
        for id in used:
            if not hasOwn(declared, id.name):
                if parent:
                    parent["used"].append(id)
                else:
                    self.raiseRecoverable(id.start, f"Private field '#{id.name}' must be declared in an enclosing class")

    def parseExportAllDeclaration(self, node, exports):
        if self.options["ecmaVersion"] >= 11:
            if self.eatContextual("as"):
                node.exported = self.parseModuleExportName()
                self.checkExport(exports, node.exported, self.lastTokStart)
            else:
                node.exported = None
        self.expectContextual("from")
        if self.type is not tt.string:
            self.unexpected()
        node.source = self.parseExprAtom()
        if self.options["ecmaVersion"] >= 16:
            node.attributes = self.parseWithClause()
        self.semicolon()
        return self.finishNode(node, "ExportAllDeclaration")

    def parseExport(self, node, exports):
        self.next()
        if self.eat(tt.star):
            return self.parseExportAllDeclaration(node, exports)
        if self.eat(tt._default):
            self.checkExport(exports, "default", self.lastTokStart)
            node.declaration = self.parseExportDefaultDeclaration()
            return self.finishNode(node, "ExportDefaultDeclaration")
        if self.shouldParseExportStatement():
            node.declaration = self.parseExportDeclaration(node)
            if node.declaration.type == "VariableDeclaration":
                self.checkVariableExport(exports, node.declaration.declarations)
            else:
                self.checkExport(exports, node.declaration.id, node.declaration.id.start)
            node.specifiers = []
            node.source = None
            if self.options["ecmaVersion"] >= 16:
                node.attributes = []
        else:
            node.declaration = None
            node.specifiers = self.parseExportSpecifiers(exports)
            if self.eatContextual("from"):
                if self.type is not tt.string:
                    self.unexpected()
                node.source = self.parseExprAtom()
                if self.options["ecmaVersion"] >= 16:
                    node.attributes = self.parseWithClause()
            else:
                for spec in node.specifiers:
                    self.checkUnreserved(spec.local)
                    self.checkLocalExport(spec.local)
                    if spec.local.type == "Literal":
                        self.raise_(spec.local.start, "A string literal cannot be used as an exported binding without `from`.")
                node.source = None
                if self.options["ecmaVersion"] >= 16:
                    node.attributes = []
            self.semicolon()
        return self.finishNode(node, "ExportNamedDeclaration")

    def parseExportDeclaration(self, node):
        return self.parseStatement(None)

    def parseExportDefaultDeclaration(self):
        isAsync = False
        if self.type is tt._function or (self.isAsyncFunction() and (isAsync := True)):
            fNode = self.startNode()
            self.next()
            if isAsync:
                self.next()
            return self.parseFunction(fNode, FUNC_STATEMENT | FUNC_NULLABLE_ID, False, isAsync)
        elif self.type is tt._class:
            cNode = self.startNode()
            return self.parseClass(cNode, "nullableID")
        else:
            declaration = self.parseMaybeAssign()
            self.semicolon()
            return declaration

    def checkExport(self, exports, name, pos):
        if exports is None:
            return
        if not isinstance(name, str):
            name = name.name if name.type == "Identifier" else name.value
        if hasOwn(exports, name):
            self.raiseRecoverable(pos, "Duplicate export '" + name + "'")
        exports[name] = True

    def checkPatternExport(self, exports, pat):
        t = pat.type
        if t == "Identifier":
            self.checkExport(exports, pat, pat.start)
        elif t == "ObjectPattern":
            for prop in pat.properties:
                self.checkPatternExport(exports, prop)
        elif t == "ArrayPattern":
            for elt in pat.elements:
                if elt:
                    self.checkPatternExport(exports, elt)
        elif t == "Property":
            self.checkPatternExport(exports, pat.value)
        elif t == "AssignmentPattern":
            self.checkPatternExport(exports, pat.left)
        elif t == "RestElement":
            self.checkPatternExport(exports, pat.argument)

    def checkVariableExport(self, exports, decls):
        if exports is None:
            return
        for decl in decls:
            self.checkPatternExport(exports, decl.id)

    def shouldParseExportStatement(self):
        return (self.type.keyword in ("var", "const", "class", "function")
                or self.isLet() or self.isAsyncFunction())

    def parseExportSpecifier(self, exports):
        node = self.startNode()
        node.local = self.parseModuleExportName()
        node.exported = self.parseModuleExportName() if self.eatContextual("as") else node.local
        self.checkExport(exports, node.exported, node.exported.start)
        return self.finishNode(node, "ExportSpecifier")

    def parseExportSpecifiers(self, exports):
        nodes = []
        first = True
        self.expect(tt.braceL)
        while not self.eat(tt.braceR):
            if not first:
                self.expect(tt.comma)
                if self.afterTrailingComma(tt.braceR):
                    break
            else:
                first = False
            nodes.append(self.parseExportSpecifier(exports))
        return nodes

    def parseImport(self, node):
        self.next()
        if self.type is tt.string:
            node.specifiers = _EMPTY
            node.source = self.parseExprAtom()
        else:
            node.specifiers = self.parseImportSpecifiers()
            self.expectContextual("from")
            node.source = self.parseExprAtom() if self.type is tt.string else self.unexpected()
        if self.options["ecmaVersion"] >= 16:
            node.attributes = self.parseWithClause()
        self.semicolon()
        return self.finishNode(node, "ImportDeclaration")

    def parseImportSpecifier(self):
        node = self.startNode()
        node.imported = self.parseModuleExportName()
        if self.eatContextual("as"):
            node.local = self.parseIdent()
        else:
            self.checkUnreserved(node.imported)
            node.local = node.imported
        self.checkLValSimple(node.local, BIND_LEXICAL)
        return self.finishNode(node, "ImportSpecifier")

    def parseImportDefaultSpecifier(self):
        node = self.startNode()
        node.local = self.parseIdent()
        self.checkLValSimple(node.local, BIND_LEXICAL)
        return self.finishNode(node, "ImportDefaultSpecifier")

    def parseImportNamespaceSpecifier(self):
        node = self.startNode()
        self.next()
        self.expectContextual("as")
        node.local = self.parseIdent()
        self.checkLValSimple(node.local, BIND_LEXICAL)
        return self.finishNode(node, "ImportNamespaceSpecifier")

    def parseImportSpecifiers(self):
        nodes = []
        first = True
        if self.type is tt.name:
            nodes.append(self.parseImportDefaultSpecifier())
            if not self.eat(tt.comma):
                return nodes
        if self.type is tt.star:
            nodes.append(self.parseImportNamespaceSpecifier())
            return nodes
        self.expect(tt.braceL)
        while not self.eat(tt.braceR):
            if not first:
                self.expect(tt.comma)
                if self.afterTrailingComma(tt.braceR):
                    break
            else:
                first = False
            nodes.append(self.parseImportSpecifier())
        return nodes

    def parseWithClause(self):
        nodes = []
        if not self.eat(tt._with):
            return nodes
        self.expect(tt.braceL)
        attributeKeys = {}
        first = True
        while not self.eat(tt.braceR):
            if not first:
                self.expect(tt.comma)
                if self.afterTrailingComma(tt.braceR):
                    break
            else:
                first = False
            attr = self.parseImportAttribute()
            keyName = attr.key.name if attr.key.type == "Identifier" else attr.key.value
            if hasOwn(attributeKeys, keyName):
                self.raiseRecoverable(attr.key.start, "Duplicate attribute key '" + keyName + "'")
            attributeKeys[keyName] = True
            nodes.append(attr)
        return nodes

    def parseImportAttribute(self):
        node = self.startNode()
        node.key = self.parseExprAtom() if self.type is tt.string else self.parseIdent(self.options["allowReserved"] != "never")
        self.expect(tt.colon)
        if self.type is not tt.string:
            self.unexpected()
        node.value = self.parseExprAtom()
        return self.finishNode(node, "ImportAttribute")

    def parseModuleExportName(self):
        if self.options["ecmaVersion"] >= 13 and self.type is tt.string:
            stringLiteral = self.parseLiteral(self.value)
            if bool(loneSurrogate.test(stringLiteral.value)):
                self.raise_(stringLiteral.start, "An export name cannot include a lone surrogate.")
            return stringLiteral
        return self.parseIdent(True)

    def adaptDirectivePrologue(self, statements):
        i = 0
        while i < len(statements) and self.isDirectiveCandidate(statements[i]):
            statements[i].directive = statements[i].expression.raw[1:-1]
            i += 1

    def isDirectiveCandidate(self, statement):
        return (self.options["ecmaVersion"] >= 5
                and statement.type == "ExpressionStatement"
                and statement.expression.type == "Literal"
                and isinstance(statement.expression.value, str)
                and (self.input[statement.start] == '"' or self.input[statement.start] == "'"))
