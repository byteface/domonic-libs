# Ported from acornjs/acorn (MIT), tag acorn@8.18.0. Mirrors src/expression.js.
"""The expression parser -- an operator-precedence core (`parseExprOp`) under a
stack of "maybe X" wrappers, down to `parseExprAtom`."""

from __future__ import annotations

from .parseutil import DestructuringErrors
from .scopeflags import (
    BIND_OUTSIDE,
    BIND_VAR,
    SCOPE_ARROW,
    SCOPE_DIRECT_SUPER,
    SCOPE_SUPER,
    SCOPE_VAR,
    functionFlags,
)
from .tokencontext import types as tokenCtxTypes
from .tokentype import tt
from .whitespace import lineBreak

_EMPTY = []


def _isLocalVariableAccess(node):
    return (node.type == "Identifier"
            or (node.type == "ParenthesizedExpression" and _isLocalVariableAccess(node.expression)))


def _isPrivateFieldAccess(node):
    return ((node.type == "MemberExpression" and node.property.type == "PrivateIdentifier")
            or (node.type == "ChainExpression" and _isPrivateFieldAccess(node.expression))
            or (node.type == "ParenthesizedExpression" and _isPrivateFieldAccess(node.expression)))


class ExpressionMixin:
    def checkPropClash(self, prop, propHash, refDestructuringErrors):
        if self.options["ecmaVersion"] >= 9 and prop.type == "SpreadElement":
            return
        if self.options["ecmaVersion"] >= 6 and (prop.computed or prop.method or prop.shorthand):
            return
        key = prop.key
        if key.type == "Identifier":
            name = key.name
        elif key.type == "Literal":
            name = str(key.value)
        else:
            return
        kind = prop.kind
        if self.options["ecmaVersion"] >= 6:
            if name == "__proto__" and kind == "init":
                if propHash.get("proto"):
                    if refDestructuringErrors:
                        if refDestructuringErrors.doubleProto < 0:
                            refDestructuringErrors.doubleProto = key.start
                    else:
                        self.raiseRecoverable(key.start, "Redefinition of __proto__ property")
                propHash["proto"] = True
            return
        name = "$" + name
        other = propHash.get(name)
        if other:
            if kind == "init":
                redefinition = (self.strict and other["init"]) or other["get"] or other["set"]
            else:
                redefinition = other["init"] or other[kind]
            if redefinition:
                self.raiseRecoverable(key.start, "Redefinition of property")
        else:
            other = propHash[name] = {"init": False, "get": False, "set": False}
        other[kind] = True

    def parseExpression(self, forInit=False, refDestructuringErrors=None):
        def body():
            startPos, startLoc = self.start, self.startLoc
            expr = self.parseMaybeAssign(forInit, refDestructuringErrors)
            if self.type is tt.comma:
                node = self.startNodeAt(startPos, startLoc)
                node.expressions = [expr]
                while self.eat(tt.comma):
                    node.expressions.append(self.parseMaybeAssign(forInit, refDestructuringErrors))
                return self.finishNode(node, "SequenceExpression")
            return expr
        return self.catchStackOverflow(body)

    def parseMaybeAssign(self, forInit=False, refDestructuringErrors=None, afterLeftParse=None):
        if self.isContextual("yield"):
            if self.inGenerator:
                return self.parseYield(forInit)
            self.exprAllowed = False

        ownDestructuringErrors = False
        oldParenAssign = oldTrailingComma = oldDoubleProto = -1
        if refDestructuringErrors:
            oldParenAssign = refDestructuringErrors.parenthesizedAssign
            oldTrailingComma = refDestructuringErrors.trailingComma
            oldDoubleProto = refDestructuringErrors.doubleProto
            refDestructuringErrors.parenthesizedAssign = refDestructuringErrors.trailingComma = -1
        else:
            refDestructuringErrors = DestructuringErrors()
            ownDestructuringErrors = True

        startPos, startLoc = self.start, self.startLoc
        if self.type is tt.parenL or self.type is tt.name:
            self.potentialArrowAt = self.start
            self.potentialArrowInForAwait = forInit == "await"
        left = self.parseMaybeConditional(forInit, refDestructuringErrors)
        if afterLeftParse:
            left = afterLeftParse(left, startPos, startLoc)
        if self.type.isAssign:
            node = self.startNodeAt(startPos, startLoc)
            node.operator = self.value
            if self.type is tt.eq:
                left = self.toAssignable(left, False, refDestructuringErrors)
            if not ownDestructuringErrors:
                refDestructuringErrors.parenthesizedAssign = refDestructuringErrors.trailingComma = -1
                if refDestructuringErrors.shorthandAssign >= left.start:
                    refDestructuringErrors.shorthandAssign = -1
                if refDestructuringErrors.doubleProto >= left.start:
                    refDestructuringErrors.doubleProto = -1
            if self.type is tt.eq:
                self.checkLValPattern(left)
            else:
                self.checkLValSimple(left)
            node.left = left
            self.next()
            node.right = self.parseMaybeAssign(forInit)
            if oldDoubleProto > -1:
                refDestructuringErrors.doubleProto = oldDoubleProto
            return self.finishNode(node, "AssignmentExpression")
        else:
            if ownDestructuringErrors:
                self.checkExpressionErrors(refDestructuringErrors, True)
        if oldParenAssign > -1:
            refDestructuringErrors.parenthesizedAssign = oldParenAssign
        if oldTrailingComma > -1:
            refDestructuringErrors.trailingComma = oldTrailingComma
        return left

    def parseMaybeConditional(self, forInit, refDestructuringErrors):
        startPos, startLoc = self.start, self.startLoc
        expr = self.parseExprOps(forInit, refDestructuringErrors)
        if self.checkExpressionErrors(refDestructuringErrors):
            return expr
        if not (expr.type == "ArrowFunctionExpression" and expr.start == startPos) and self.eat(tt.question):
            node = self.startNodeAt(startPos, startLoc)
            node.test = expr
            node.consequent = self.parseMaybeAssign()
            self.expect(tt.colon)
            node.alternate = self.parseMaybeAssign(forInit)
            return self.finishNode(node, "ConditionalExpression")
        return expr

    def parseExprOps(self, forInit, refDestructuringErrors):
        startPos, startLoc = self.start, self.startLoc
        expr = self.parseMaybeUnary(refDestructuringErrors, False, False, forInit)
        if self.checkExpressionErrors(refDestructuringErrors):
            return expr
        if expr.start == startPos and expr.type == "ArrowFunctionExpression":
            return expr
        return self.parseExprOp(expr, startPos, startLoc, -1, forInit)

    def parseExprOp(self, left, leftStartPos, leftStartLoc, minPrec, forInit):
        prec = self.type.binop
        if prec is not None and (not forInit or self.type is not tt._in):
            if prec > minPrec:
                logical = self.type is tt.logicalOR or self.type is tt.logicalAND
                coalesce = self.type is tt.coalesce
                if coalesce:
                    prec = tt.logicalAND.binop
                op = self.value
                self.next()
                startPos, startLoc = self.start, self.startLoc
                right = self.parseExprOp(self.parseMaybeUnary(None, False, False, forInit), startPos, startLoc, prec, forInit)
                node = self.buildBinary(leftStartPos, leftStartLoc, left, right, op, logical or coalesce)
                if (logical and self.type is tt.coalesce) or (coalesce and (self.type is tt.logicalOR or self.type is tt.logicalAND)):
                    self.raiseRecoverable(self.start, "Logical expressions and coalesce expressions cannot be mixed. Wrap either by parentheses")
                return self.parseExprOp(node, leftStartPos, leftStartLoc, minPrec, forInit)
        return left

    def buildBinary(self, startPos, startLoc, left, right, op, logical):
        if right.type == "PrivateIdentifier":
            self.raise_(right.start, "Private identifier can only be left side of binary expression")
        node = self.startNodeAt(startPos, startLoc)
        node.left = left
        node.operator = op
        node.right = right
        return self.finishNode(node, "LogicalExpression" if logical else "BinaryExpression")

    def parseMaybeUnary(self, refDestructuringErrors, sawUnary, incDec, forInit):
        startPos, startLoc = self.start, self.startLoc
        if self.isContextual("await") and self.canAwait:
            expr = self.parseAwait(forInit)
            sawUnary = True
        elif self.type.prefix:
            node = self.startNode()
            update = self.type is tt.incDec
            node.operator = self.value
            node.prefix = True
            self.next()
            node.argument = self.parseMaybeUnary(None, True, update, forInit)
            self.checkExpressionErrors(refDestructuringErrors, True)
            if update:
                self.checkLValSimple(node.argument)
            elif self.strict and node.operator == "delete" and _isLocalVariableAccess(node.argument):
                self.raiseRecoverable(node.start, "Deleting local variable in strict mode")
            elif node.operator == "delete" and _isPrivateFieldAccess(node.argument):
                self.raiseRecoverable(node.start, "Private fields can not be deleted")
            else:
                sawUnary = True
            expr = self.finishNode(node, "UpdateExpression" if update else "UnaryExpression")
        elif not sawUnary and self.type is tt.privateId:
            if (forInit or len(self.privateNameStack) == 0) and self.options["checkPrivateFields"]:
                self.unexpected()
            expr = self.parsePrivateIdent()
            if self.type is not tt._in:
                self.unexpected()
        else:
            expr = self.parseExprSubscripts(refDestructuringErrors, forInit)
            if self.checkExpressionErrors(refDestructuringErrors):
                return expr
            while self.type.postfix and not self.canInsertSemicolon():
                node = self.startNodeAt(startPos, startLoc)
                node.operator = self.value
                node.prefix = False
                node.argument = expr
                self.checkLValSimple(expr)
                self.next()
                expr = self.finishNode(node, "UpdateExpression")

        if not incDec and not (expr.type == "ArrowFunctionExpression" and expr.start == startPos) and self.eat(tt.starstar):
            if sawUnary:
                self.unexpected(self.lastTokStart)
            return self.buildBinary(startPos, startLoc, expr, self.parseMaybeUnary(None, False, False, forInit), "**", False)
        return expr

    def parseExprSubscripts(self, refDestructuringErrors, forInit):
        startPos, startLoc = self.start, self.startLoc
        oldDoubleProto = oldShorthandAssign = -1
        if refDestructuringErrors:
            oldDoubleProto = refDestructuringErrors.doubleProto
            oldShorthandAssign = refDestructuringErrors.shorthandAssign
            refDestructuringErrors.doubleProto = refDestructuringErrors.shorthandAssign = -1
        expr = self.parseExprAtom(refDestructuringErrors, forInit)
        if expr.type == "ArrowFunctionExpression" and str(self.input.slice(self.lastTokStart, self.lastTokEnd)) != ")":
            return expr
        result = self.parseSubscripts(expr, startPos, startLoc, False, forInit)
        if refDestructuringErrors:
            if result.end > expr.end:
                self.checkExpressionErrors(refDestructuringErrors, True)
                if refDestructuringErrors.parenthesizedAssign >= result.start:
                    refDestructuringErrors.parenthesizedAssign = -1
                if refDestructuringErrors.parenthesizedBind >= result.start:
                    refDestructuringErrors.parenthesizedBind = -1
                if refDestructuringErrors.trailingComma >= result.start:
                    refDestructuringErrors.trailingComma = -1
            if oldDoubleProto > -1:
                refDestructuringErrors.doubleProto = oldDoubleProto
            if oldShorthandAssign > -1:
                refDestructuringErrors.shorthandAssign = oldShorthandAssign
        return result

    def parseSubscripts(self, base, startPos, startLoc, noCalls, forInit):
        maybeAsyncArrow = (self.options["ecmaVersion"] >= 8 and base.type == "Identifier" and base.name == "async"
                           and self.lastTokEnd == base.end and not self.canInsertSemicolon()
                           and base.end - base.start == 5 and self.potentialArrowAt == base.start)
        optionalChained = False
        while True:
            element = self.parseSubscript(base, startPos, startLoc, noCalls, maybeAsyncArrow, optionalChained, forInit)
            if getattr(element, "optional", False):
                optionalChained = True
            if element.end == base.end or element.type == "ArrowFunctionExpression":
                if optionalChained:
                    chainNode = self.startNodeAt(startPos, startLoc)
                    chainNode.expression = element
                    element = self.finishNode(chainNode, "ChainExpression")
                return element
            base = element

    def shouldParseAsyncArrow(self):
        return not self.canInsertSemicolon() and self.eat(tt.arrow)

    def parseSubscriptAsyncArrow(self, startPos, startLoc, exprList, forInit):
        return self.parseArrowExpression(self.startNodeAt(startPos, startLoc), exprList, True, forInit)

    def parseSubscript(self, base, startPos, startLoc, noCalls, maybeAsyncArrow, optionalChained, forInit):
        optionalSupported = self.options["ecmaVersion"] >= 11
        optional = optionalSupported and self.eat(tt.questionDot)
        if noCalls and optional:
            self.raise_(self.lastTokStart, "Optional chaining cannot appear in the callee of new expressions")
        computed = self.eat(tt.bracketL)
        if computed or (optional and self.type is not tt.parenL and self.type is not tt.backQuote) or self.eat(tt.dot):
            node = self.startNodeAt(startPos, startLoc)
            node.object = base
            if computed:
                node.property = self.parseExpression()
                self.expect(tt.bracketR)
            elif self.type is tt.privateId and base.type != "Super":
                node.property = self.parsePrivateIdent()
            else:
                node.property = self.parseIdent(self.options["allowReserved"] != "never")
            node.computed = bool(computed)
            if optionalSupported:
                node.optional = optional
            base = self.finishNode(node, "MemberExpression")
        elif not noCalls and self.eat(tt.parenL):
            refDestructuringErrors = DestructuringErrors()
            oldYieldPos, oldAwaitPos, oldAwaitIdentPos = self.yieldPos, self.awaitPos, self.awaitIdentPos
            self.yieldPos = self.awaitPos = self.awaitIdentPos = 0
            exprList = self.parseExprList(tt.parenR, self.options["ecmaVersion"] >= 8, False, refDestructuringErrors)
            if maybeAsyncArrow and not optional and self.shouldParseAsyncArrow():
                self.checkPatternErrors(refDestructuringErrors, False)
                self.checkYieldAwaitInDefaultParams()
                if self.awaitIdentPos > 0:
                    self.raise_(self.awaitIdentPos, "Cannot use 'await' as identifier inside an async function")
                self.yieldPos, self.awaitPos, self.awaitIdentPos = oldYieldPos, oldAwaitPos, oldAwaitIdentPos
                return self.parseSubscriptAsyncArrow(startPos, startLoc, exprList, forInit)
            self.checkExpressionErrors(refDestructuringErrors, True)
            self.yieldPos = oldYieldPos or self.yieldPos
            self.awaitPos = oldAwaitPos or self.awaitPos
            self.awaitIdentPos = oldAwaitIdentPos or self.awaitIdentPos
            node = self.startNodeAt(startPos, startLoc)
            node.callee = base
            node.arguments = exprList
            if optionalSupported:
                node.optional = optional
            base = self.finishNode(node, "CallExpression")
        elif self.type is tt.backQuote:
            if optional or optionalChained:
                self.raise_(self.start, "Optional chaining cannot appear in the tag of tagged template expressions")
            node = self.startNodeAt(startPos, startLoc)
            node.tag = base
            node.quasi = self.parseTemplate(isTagged=True)
            base = self.finishNode(node, "TaggedTemplateExpression")
        return base

    def parseExprAtom(self, refDestructuringErrors=None, forInit=False, forNew=False):
        if self.type is tt.slash:
            self.readRegexp()
        canBeArrow = self.potentialArrowAt == self.start
        t = self.type
        if t is tt._super:
            if not self.allowSuper:
                self.raise_(self.start, "'super' keyword outside a method")
            node = self.startNode()
            self.next()
            if self.type is tt.parenL and not self.allowDirectSuper:
                self.raise_(node.start, "super() call outside constructor of a subclass")
            if self.type is not tt.dot and self.type is not tt.bracketL and self.type is not tt.parenL:
                self.unexpected()
            return self.finishNode(node, "Super")
        if t is tt._this:
            node = self.startNode()
            self.next()
            return self.finishNode(node, "ThisExpression")
        if t is tt.name:
            startPos, startLoc, containsEsc = self.start, self.startLoc, self.containsEsc
            id = self.parseIdent(False)
            if self.options["ecmaVersion"] >= 8 and not containsEsc and id.name == "async" and not self.canInsertSemicolon() and self.eat(tt._function):
                self.overrideContext(tokenCtxTypes["f_expr"])
                return self.parseFunction(self.startNodeAt(startPos, startLoc), 0, False, True, forInit)
            if canBeArrow and not self.canInsertSemicolon():
                if self.eat(tt.arrow):
                    return self.parseArrowExpression(self.startNodeAt(startPos, startLoc), [id], False, forInit)
                if (self.options["ecmaVersion"] >= 8 and id.name == "async" and self.type is tt.name and not containsEsc
                        and (not self.potentialArrowInForAwait or self.value != "of" or self.containsEsc)):
                    id = self.parseIdent(False)
                    if self.canInsertSemicolon() or not self.eat(tt.arrow):
                        self.unexpected()
                    return self.parseArrowExpression(self.startNodeAt(startPos, startLoc), [id], True, forInit)
            return id
        if t is tt.regexp:
            value = self.value
            node = self.parseLiteral(value["value"])
            node.regex = {"pattern": value["pattern"], "flags": value["flags"]}
            return node
        if t is tt.num or t is tt.string:
            return self.parseLiteral(self.value)
        if t is tt._null or t is tt._true or t is tt._false:
            node = self.startNode()
            node.value = None if self.type is tt._null else (self.type is tt._true)
            node.raw = self.type.keyword
            self.next()
            return self.finishNode(node, "Literal")
        if t is tt.parenL:
            start = self.start
            expr = self.parseParenAndDistinguishExpression(canBeArrow, forInit)
            if refDestructuringErrors:
                if refDestructuringErrors.parenthesizedAssign < 0 and not self.isSimpleAssignTarget(expr):
                    refDestructuringErrors.parenthesizedAssign = start
                if refDestructuringErrors.parenthesizedBind < 0:
                    refDestructuringErrors.parenthesizedBind = start
            return expr
        if t is tt.bracketL:
            node = self.startNode()
            self.next()
            node.elements = self.parseExprList(tt.bracketR, True, True, refDestructuringErrors)
            return self.finishNode(node, "ArrayExpression")
        if t is tt.braceL:
            self.overrideContext(tokenCtxTypes["b_expr"])
            return self.parseObj(False, refDestructuringErrors)
        if t is tt._function:
            node = self.startNode()
            self.next()
            return self.parseFunction(node, 0)
        if t is tt._class:
            return self.parseClass(self.startNode(), False)
        if t is tt._new:
            return self.parseNew()
        if t is tt.backQuote:
            return self.parseTemplate()
        if t is tt._import:
            if self.options["ecmaVersion"] >= 11:
                return self.parseExprImport(forNew)
            return self.unexpected()
        return self.parseExprAtomDefault()

    def parseExprAtomDefault(self):
        self.unexpected()

    def parseExprImport(self, forNew):
        node = self.startNode()
        if self.containsEsc:
            self.raiseRecoverable(self.start, "Escape sequence in keyword import")
        self.next()
        if self.type is tt.parenL and not forNew:
            return self.parseDynamicImport(node)
        elif self.type is tt.dot:
            meta = self.startNodeAt(node.start, node.loc.start if getattr(node, "loc", None) else None)
            meta.name = "import"
            node.meta = self.finishNode(meta, "Identifier")
            return self.parseImportMeta(node)
        else:
            self.unexpected()

    def parseDynamicImport(self, node):
        self.next()
        node.source = self.parseMaybeAssign()
        if self.options["ecmaVersion"] >= 16:
            if not self.eat(tt.parenR):
                self.expect(tt.comma)
                if not self.afterTrailingComma(tt.parenR):
                    node.options = self.parseMaybeAssign()
                    if not self.eat(tt.parenR):
                        self.expect(tt.comma)
                        if not self.afterTrailingComma(tt.parenR):
                            self.unexpected()
                else:
                    node.options = None
            else:
                node.options = None
        else:
            if not self.eat(tt.parenR):
                errorPos = self.start
                if self.eat(tt.comma) and self.eat(tt.parenR):
                    self.raiseRecoverable(errorPos, "Trailing comma is not allowed in import()")
                else:
                    self.unexpected(errorPos)
        return self.finishNode(node, "ImportExpression")

    def parseImportMeta(self, node):
        self.next()
        containsEsc = self.containsEsc
        node.property = self.parseIdent(True)
        if node.property.name != "meta":
            self.raiseRecoverable(node.property.start, "The only valid meta property for import is 'import.meta'")
        if containsEsc:
            self.raiseRecoverable(node.start, "'import.meta' must not contain escaped characters")
        if self.options["sourceType"] != "module" and not self.options["allowImportExportEverywhere"]:
            self.raiseRecoverable(node.start, "Cannot use 'import.meta' outside a module")
        return self.finishNode(node, "MetaProperty")

    def parseLiteral(self, value):
        node = self.startNode()
        node.value = value
        node.raw = str(self.input.slice(self.start, self.end))
        if node.raw and ord(node.raw[-1]) == 110:
            node.bigint = (str(node.value) if node.value is not None
                           else node.raw[:-1].replace("_", ""))
        self.next()
        return self.finishNode(node, "Literal")

    def parseParenExpression(self):
        self.expect(tt.parenL)
        val = self.parseExpression()
        self.expect(tt.parenR)
        return val

    def shouldParseArrow(self, exprList):
        return not self.canInsertSemicolon()

    def parseParenAndDistinguishExpression(self, canBeArrow, forInit):
        startPos, startLoc = self.start, self.startLoc
        allowTrailingComma = self.options["ecmaVersion"] >= 8
        val = None
        if self.options["ecmaVersion"] >= 6:
            self.next()
            innerStartPos, innerStartLoc = self.start, self.startLoc
            exprList = []
            first = True
            lastIsComma = False
            refDestructuringErrors = DestructuringErrors()
            oldYieldPos, oldAwaitPos = self.yieldPos, self.awaitPos
            spreadStart = None
            self.yieldPos = self.awaitPos = 0
            while self.type is not tt.parenR:
                if first:
                    first = False
                else:
                    self.expect(tt.comma)
                if allowTrailingComma and self.afterTrailingComma(tt.parenR, True):
                    lastIsComma = True
                    break
                elif self.type is tt.ellipsis:
                    spreadStart = self.start
                    exprList.append(self.parseParenItem(self.parseRestBinding()))
                    if self.type is tt.comma:
                        self.raiseRecoverable(self.start, "Comma is not permitted after the rest element")
                    break
                else:
                    exprList.append(self.parseMaybeAssign(False, refDestructuringErrors, self.parseParenItem))
            innerEndPos, innerEndLoc = self.lastTokEnd, self.lastTokEndLoc
            self.expect(tt.parenR)
            if canBeArrow and self.shouldParseArrow(exprList) and self.eat(tt.arrow):
                self.checkPatternErrors(refDestructuringErrors, False)
                self.checkYieldAwaitInDefaultParams()
                self.yieldPos, self.awaitPos = oldYieldPos, oldAwaitPos
                return self.parseParenArrowList(startPos, startLoc, exprList, forInit)
            if not exprList or lastIsComma:
                self.unexpected(self.lastTokStart)
            if spreadStart is not None:
                self.unexpected(spreadStart)
            self.checkExpressionErrors(refDestructuringErrors, True)
            self.yieldPos = oldYieldPos or self.yieldPos
            self.awaitPos = oldAwaitPos or self.awaitPos
            if len(exprList) > 1:
                val = self.startNodeAt(innerStartPos, innerStartLoc)
                val.expressions = exprList
                self.finishNodeAt(val, "SequenceExpression", innerEndPos, innerEndLoc)
            else:
                val = exprList[0]
        else:
            val = self.parseParenExpression()
        if self.options["preserveParens"]:
            par = self.startNodeAt(startPos, startLoc)
            par.expression = val
            return self.finishNode(par, "ParenthesizedExpression")
        return val

    def parseParenItem(self, item, *_):
        # passed as `afterLeftParse` -> called with (item, startPos, startLoc)
        return item

    def parseParenArrowList(self, startPos, startLoc, exprList, forInit):
        return self.parseArrowExpression(self.startNodeAt(startPos, startLoc), exprList, False, forInit)

    def parseNew(self):
        if self.containsEsc:
            self.raiseRecoverable(self.start, "Escape sequence in keyword new")
        node = self.startNode()
        self.next()
        if self.options["ecmaVersion"] >= 6 and self.type is tt.dot:
            meta = self.startNodeAt(node.start, node.loc.start if getattr(node, "loc", None) else None)
            meta.name = "new"
            node.meta = self.finishNode(meta, "Identifier")
            self.next()
            containsEsc = self.containsEsc
            node.property = self.parseIdent(True)
            if node.property.name != "target":
                self.raiseRecoverable(node.property.start, "The only valid meta property for new is 'new.target'")
            if containsEsc:
                self.raiseRecoverable(node.start, "'new.target' must not contain escaped characters")
            if not self.allowNewDotTarget:
                self.raiseRecoverable(node.start, "'new.target' can only be used in functions and class static block")
            return self.finishNode(node, "MetaProperty")
        startPos, startLoc = self.start, self.startLoc
        node.callee = self.parseSubscripts(self.parseExprAtom(None, False, True), startPos, startLoc, True, False)
        if node.callee.type == "Super":
            self.raiseRecoverable(startPos, "Invalid use of 'super'")
        if self.eat(tt.parenL):
            node.arguments = self.parseExprList(tt.parenR, self.options["ecmaVersion"] >= 8, False)
        else:
            node.arguments = _EMPTY
        return self.finishNode(node, "NewExpression")

    def parseTemplateElement(self, isTagged):
        elem = self.startNode()
        if self.type is tt.invalidTemplate:
            if not isTagged:
                self.raiseRecoverable(self.start, "Bad escape sequence in untagged template literal")
            elem.value = {"raw": _crlf(self.value), "cooked": None}
        else:
            elem.value = {"raw": _crlf(str(self.input.slice(self.start, self.end))), "cooked": self.value}
        self.next()
        elem.tail = self.type is tt.backQuote
        return self.finishNode(elem, "TemplateElement")

    def parseTemplate(self, isTagged=False):
        node = self.startNode()
        self.next()
        node.expressions = []
        curElt = self.parseTemplateElement(isTagged)
        node.quasis = [curElt]
        while not curElt.tail:
            if self.type is tt.eof:
                self.raise_(self.pos, "Unterminated template literal")
            self.expect(tt.dollarBraceL)
            node.expressions.append(self.parseExpression())
            self.expect(tt.braceR)
            curElt = self.parseTemplateElement(isTagged)
            node.quasis.append(curElt)
        self.next()
        return self.finishNode(node, "TemplateLiteral")

    def isAsyncProp(self, prop):
        return (not prop.computed and prop.key.type == "Identifier" and prop.key.name == "async"
                and (self.type is tt.name or self.type is tt.num or self.type is tt.string or self.type is tt.bracketL
                     or self.type.keyword or (self.options["ecmaVersion"] >= 9 and self.type is tt.star))
                and not bool(lineBreak.test(self.input.slice(self.lastTokEnd, self.start))))

    def parseObj(self, isPattern, refDestructuringErrors=None):
        node = self.startNode()
        first = True
        propHash = {}
        node.properties = []
        self.next()
        while not self.eat(tt.braceR):
            if not first:
                self.expect(tt.comma)
                if self.options["ecmaVersion"] >= 5 and self.afterTrailingComma(tt.braceR):
                    break
            else:
                first = False
            prop = self.parseProperty(isPattern, refDestructuringErrors)
            if not isPattern:
                self.checkPropClash(prop, propHash, refDestructuringErrors)
            node.properties.append(prop)
        return self.finishNode(node, "ObjectPattern" if isPattern else "ObjectExpression")

    def parseProperty(self, isPattern, refDestructuringErrors):
        prop = self.startNode()
        isGenerator = False
        isAsync = False
        startPos = startLoc = None
        if self.options["ecmaVersion"] >= 9 and self.eat(tt.ellipsis):
            if isPattern:
                prop.argument = self.parseIdent(False)
                if self.type is tt.comma:
                    self.raiseRecoverable(self.start, "Comma is not permitted after the rest element")
                return self.finishNode(prop, "RestElement")
            prop.argument = self.parseMaybeAssign(False, refDestructuringErrors)
            if self.type is tt.comma and refDestructuringErrors and refDestructuringErrors.trailingComma < 0:
                refDestructuringErrors.trailingComma = self.start
            return self.finishNode(prop, "SpreadElement")
        if self.options["ecmaVersion"] >= 6:
            prop.method = False
            prop.shorthand = False
            if isPattern or refDestructuringErrors:
                startPos, startLoc = self.start, self.startLoc
            if not isPattern:
                isGenerator = self.eat(tt.star)
        containsEsc = self.containsEsc
        self.parsePropertyName(prop)
        if (not isPattern and not containsEsc and self.options["ecmaVersion"] >= 8 and not isGenerator
                and self.isAsyncProp(prop)):
            isAsync = True
            isGenerator = self.options["ecmaVersion"] >= 9 and self.eat(tt.star)
            self.parsePropertyName(prop)
        else:
            isAsync = False
        self.parsePropertyValue(prop, isPattern, isGenerator, isAsync, startPos, startLoc, refDestructuringErrors, containsEsc)
        return self.finishNode(prop, "Property")

    def parseGetterSetter(self, prop):
        kind = prop.key.name
        self.parsePropertyName(prop)
        prop.value = self.parseMethod(False)
        prop.kind = kind
        paramCount = 0 if prop.kind == "get" else 1
        if len(prop.value.params) != paramCount:
            start = prop.value.start
            if prop.kind == "get":
                self.raiseRecoverable(start, "getter should have no params")
            else:
                self.raiseRecoverable(start, "setter should have exactly one param")
        else:
            if prop.kind == "set" and prop.value.params[0].type == "RestElement":
                self.raiseRecoverable(prop.value.params[0].start, "Setter cannot use rest params")

    def parsePropertyValue(self, prop, isPattern, isGenerator, isAsync, startPos, startLoc, refDestructuringErrors, containsEsc):
        if (isGenerator or isAsync) and self.type is tt.colon:
            self.unexpected()
        if self.eat(tt.colon):
            prop.value = (self.parseMaybeDefault(self.start, self.startLoc) if isPattern
                          else self.parseMaybeAssign(False, refDestructuringErrors))
            prop.kind = "init"
        elif self.options["ecmaVersion"] >= 6 and self.type is tt.parenL:
            if isPattern:
                self.unexpected()
            prop.method = True
            prop.value = self.parseMethod(isGenerator, isAsync)
            prop.kind = "init"
        elif (not isPattern and not containsEsc and self.options["ecmaVersion"] >= 5 and not prop.computed
              and prop.key.type == "Identifier" and (prop.key.name == "get" or prop.key.name == "set")
              and self.type is not tt.comma and self.type is not tt.braceR and self.type is not tt.eq):
            if isGenerator or isAsync:
                self.unexpected()
            self.parseGetterSetter(prop)
        elif self.options["ecmaVersion"] >= 6 and not prop.computed and prop.key.type == "Identifier":
            if isGenerator or isAsync:
                self.unexpected()
            self.checkUnreserved(prop.key)
            if prop.key.name == "await" and not self.awaitIdentPos:
                self.awaitIdentPos = startPos
            if isPattern:
                prop.value = self.parseMaybeDefault(startPos, startLoc, self.copyNode(prop.key))
            elif self.type is tt.eq and refDestructuringErrors:
                if refDestructuringErrors.shorthandAssign < 0:
                    refDestructuringErrors.shorthandAssign = self.start
                prop.value = self.parseMaybeDefault(startPos, startLoc, self.copyNode(prop.key))
            else:
                prop.value = self.copyNode(prop.key)
            prop.kind = "init"
            prop.shorthand = True
        else:
            self.unexpected()

    def parsePropertyName(self, prop):
        if self.options["ecmaVersion"] >= 6:
            if self.eat(tt.bracketL):
                prop.computed = True
                prop.key = self.parseMaybeAssign()
                self.expect(tt.bracketR)
                return prop.key
            prop.computed = False
        prop.key = (self.parseExprAtom() if self.type is tt.num or self.type is tt.string
                    else self.parseIdent(self.options["allowReserved"] != "never"))
        return prop.key

    def initFunction(self, node):
        # `async` is a Python keyword, so the ESTree `async` field lives in
        # __dict__ and is read back with getattr(node, "async", ...).
        node.id = None
        if self.options["ecmaVersion"] >= 6:
            node.generator = node.expression = False
        if self.options["ecmaVersion"] >= 8:
            node.__dict__["async"] = False

    def parseMethod(self, isGenerator, isAsync=False, allowDirectSuper=False):
        node = self.startNode()
        oldYieldPos, oldAwaitPos, oldAwaitIdentPos = self.yieldPos, self.awaitPos, self.awaitIdentPos
        self.initFunction(node)
        if self.options["ecmaVersion"] >= 6:
            node.generator = isGenerator
        if self.options["ecmaVersion"] >= 8:
            node.__dict__["async"] = bool(isAsync)
        self.yieldPos = self.awaitPos = self.awaitIdentPos = 0
        self.enterScope(functionFlags(isAsync, node.generator) | SCOPE_SUPER | (SCOPE_DIRECT_SUPER if allowDirectSuper else 0))
        self.expect(tt.parenL)
        node.params = self.parseBindingList(tt.parenR, False, self.options["ecmaVersion"] >= 8)
        self.checkYieldAwaitInDefaultParams()
        self.parseFunctionBody(node, False, True, False)
        self.yieldPos, self.awaitPos, self.awaitIdentPos = oldYieldPos, oldAwaitPos, oldAwaitIdentPos
        return self.finishNode(node, "FunctionExpression")

    def parseArrowExpression(self, node, params, isAsync, forInit=False):
        oldYieldPos, oldAwaitPos, oldAwaitIdentPos = self.yieldPos, self.awaitPos, self.awaitIdentPos
        self.enterScope(functionFlags(isAsync, False) | SCOPE_ARROW)
        self.initFunction(node)
        if self.options["ecmaVersion"] >= 8:
            node.__dict__["async"] = bool(isAsync)
        self.yieldPos = self.awaitPos = self.awaitIdentPos = 0
        node.params = self.toAssignableList(params, True)
        self.parseFunctionBody(node, True, False, forInit)
        self.yieldPos, self.awaitPos, self.awaitIdentPos = oldYieldPos, oldAwaitPos, oldAwaitIdentPos
        return self.finishNode(node, "ArrowFunctionExpression")

    def parseFunctionBody(self, node, isArrowFunction, isMethod, forInit):
        isExpression = isArrowFunction and self.type is not tt.braceL
        oldStrict = self.strict
        useStrict = False
        if isExpression:
            node.body = self.parseMaybeAssign(forInit)
            node.expression = True
            self.checkParams(node, False)
        else:
            nonSimple = self.options["ecmaVersion"] >= 7 and not self.isSimpleParamList(node.params)
            if not oldStrict or nonSimple:
                useStrict = self.strictDirective(self.end)
                if useStrict and nonSimple:
                    self.raiseRecoverable(node.start, "Illegal 'use strict' directive in function with non-simple parameter list")
            oldLabels = self.labels
            self.labels = []
            if useStrict:
                self.strict = True
            self.checkParams(node, not oldStrict and not useStrict and not isArrowFunction and not isMethod and self.isSimpleParamList(node.params))
            if self.strict and node.id:
                self.checkLValSimple(node.id, BIND_OUTSIDE)
            node.body = self.parseBlock(False, None, useStrict and not oldStrict)
            node.expression = False
            self.adaptDirectivePrologue(node.body.body)
            self.labels = oldLabels
        self.exitScope()

    def isSimpleParamList(self, params):
        for param in params:
            if param.type != "Identifier":
                return False
        return True

    def checkParams(self, node, allowDuplicates):
        nameHash = None if allowDuplicates else {}
        for param in node.params:
            self.checkLValInnerPattern(param, BIND_VAR, nameHash)

    def parseExprList(self, close, allowTrailingComma, allowEmpty, refDestructuringErrors=None):
        elts = []
        first = True
        while not self.eat(close):
            if not first:
                self.expect(tt.comma)
                if allowTrailingComma and self.afterTrailingComma(close):
                    break
            else:
                first = False
            if allowEmpty and self.type is tt.comma:
                elt = None
            elif self.type is tt.ellipsis:
                elt = self.parseSpread(refDestructuringErrors)
                if refDestructuringErrors and self.type is tt.comma and refDestructuringErrors.trailingComma < 0:
                    refDestructuringErrors.trailingComma = self.start
            else:
                elt = self.parseMaybeAssign(False, refDestructuringErrors)
            elts.append(elt)
        return elts

    def checkUnreserved(self, node):
        start, end, name = node.start, node.end, node.name
        if self.inGenerator and name == "yield":
            self.raiseRecoverable(start, "Cannot use 'yield' as identifier inside a generator")
        if self.inAsync and name == "await":
            self.raiseRecoverable(start, "Cannot use 'await' as identifier inside an async function")
        if not (self.currentThisScope().flags & SCOPE_VAR) and name == "arguments":
            self.raiseRecoverable(start, "Cannot use 'arguments' in class field initializer")
        if self.inClassStaticBlock and (name == "arguments" or name == "await"):
            self.raise_(start, f"Cannot use {name} in class static initialization block")
        if bool(self.keywords.test(name)):
            self.raise_(start, f"Unexpected keyword '{name}'")
        if self.options["ecmaVersion"] < 6 and str(self.input.slice(start, end)).find("\\") != -1:
            return
        re = self.reservedWordsStrict if self.strict else self.reservedWords
        if bool(re.test(name)):
            if not self.inAsync and name == "await":
                self.raiseRecoverable(start, "Cannot use keyword 'await' outside an async function")
            self.raiseRecoverable(start, f"The keyword '{name}' is reserved")

    def parseIdent(self, liberal=False):
        node = self.parseIdentNode()
        self.next(bool(liberal))
        self.finishNode(node, "Identifier")
        if not liberal:
            self.checkUnreserved(node)
            if node.name == "await" and not self.awaitIdentPos:
                self.awaitIdentPos = node.start
        return node

    def parseIdentNode(self):
        node = self.startNode()
        if self.type is tt.name:
            node.name = self.value
        elif self.type.keyword:
            node.name = self.type.keyword
            if ((node.name == "class" or node.name == "function")
                    and (self.lastTokEnd != self.lastTokStart + 1 or self.input.charCodeAt(self.lastTokStart) != 46)):
                self.context.pop()
            self.type = tt.name
        else:
            self.unexpected()
        return node

    def parsePrivateIdent(self):
        node = self.startNode()
        if self.type is tt.privateId:
            node.name = self.value
        else:
            self.unexpected()
        self.next()
        self.finishNode(node, "PrivateIdentifier")
        if self.options["checkPrivateFields"]:
            if len(self.privateNameStack) == 0:
                self.raise_(node.start, f"Private field '#{node.name}' must be declared in an enclosing class")
            else:
                self.privateNameStack[-1]["used"].append(node)
        return node

    def parseYield(self, forInit):
        if not self.yieldPos:
            self.yieldPos = self.start
        node = self.startNode()
        self.next()
        if self.type is tt.semi or self.canInsertSemicolon() or (self.type is not tt.star and not self.type.startsExpr):
            node.delegate = False
            node.argument = None
        else:
            node.delegate = self.eat(tt.star)
            node.argument = self.parseMaybeAssign(forInit)
        return self.finishNode(node, "YieldExpression")

    def parseAwait(self, forInit):
        if not self.awaitPos:
            self.awaitPos = self.start
        node = self.startNode()
        self.next()
        node.argument = self.parseMaybeUnary(None, True, False, forInit)
        return self.finishNode(node, "AwaitExpression")


def _crlf(s):
    from domonic.javascript import RegExp, String
    return str(String(s).replace(RegExp(r"\r\n?", "g"), "\n"))
