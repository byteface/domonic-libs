CLIENT_SCRIPT = """
window.__domonicUI = {
    timers: {},
    fileDropInstalled: false,

    // Events that fire in bursts (a slider drag, a scroll, a pointer move).
    // Only the newest matters, so while a round-trip is in flight we keep just
    // the latest and send it when the current one resolves.
    highFrequencyEvents: {
        input: true, pointermove: true, mousemove: true, drag: true,
        scroll: true, wheel: true, touchmove: true
    },
    busy: false,
    pendingSend: null,

    // Transport seam. DesktopApp leaves `transport` unset and the calls go
    // through pywebview's injected `pywebview.api`; BrowserApp assigns a
    // fetch-based function (see web._TRANSPORT_JS).
    transport: null,

    rpc: function (method) {
        var args = Array.prototype.slice.call(arguments, 1);
        if (typeof this.transport === "function") {
            return this.transport(method, args);
        }
        return window.pywebview.api[method].apply(window.pywebview.api, args);
    },

    startTimer: function (timerId, interval) {
        if (this.timers[timerId]) {
            clearInterval(this.timers[timerId]);
        }

        this.timers[timerId] = setInterval(function () {
            window.__domonicUI.rpc("tick", timerId).then(function (response) {
                window.__domonicUI.applyResponse(response, null);
            });
        }, interval);
    },

    dispatch: function (event, handlerId) {
        if (event.type === "submit") {
            event.preventDefault();
        }

        var self = this;
        var payload = this.eventPayload(event);
        var focusState = this.captureFocus();

        var send = function () {
            self.busy = true;
            self.rpc("dispatch", handlerId, payload)
                .then(function (response) {
                    self.busy = false;
                    self.applyResponse(response, focusState);
                    self.flushPending();
                })
                .catch(function (error) {
                    self.busy = false;
                    console.error("domonic-libs event failed", error);
                    self.flushPending();
                });
        };

        if (this.highFrequencyEvents[event.type] && this.busy) {
            this.pendingSend = send;
        } else {
            send();
        }

        return event.type === "submit" ? false : true;
    },

    flushPending: function () {
        var pending = this.pendingSend;
        if (pending) {
            this.pendingSend = null;
            pending();
        }
    },

    startFileDrop: function () {
        if (this.fileDropInstalled) {
            return;
        }

        this.fileDropInstalled = true;

        window.addEventListener("dragover", function (event) {
            event.preventDefault();
            document.body.classList.add("domonic-libs-dragging");
        });

        window.addEventListener("dragleave", function (event) {
            if (event.target === document.body || event.clientX === 0 && event.clientY === 0) {
                document.body.classList.remove("domonic-libs-dragging");
            }
        });

        window.addEventListener("drop", function (event) {
            event.preventDefault();
            document.body.classList.remove("domonic-libs-dragging");

            window.__domonicUI.rpc(
                "file_drop",
                window.__domonicUI.filesFromDataTransfer(event.dataTransfer)
            )
                .then(function (response) {
                    window.__domonicUI.applyResponse(response, null);
                })
                .catch(function (error) {
                    console.error("domonic-libs file drop failed", error);
                });
        });
    },

    applyResponse: function (response, focusState) {
        if (response && typeof response.html === "string") {
            this.applyHTML(response.html);

            if (focusState) {
                window.__domonicUI.restoreFocus(focusState);
            }
        }

        if (response && response.commands) {
            window.__domonicUI.applyCommands(response.commands);
        }

        if (response && response.error) {
            console.error(response.error.traceback || response.error.message);
        }
    },

    applyCommands: function (commands) {
        var self = this;
        (commands || []).forEach(function (command) {
            if (!command || !command.op) {
                return;
            }
            if (command.op === "html") {
                self.applyHTML(command.html);
            } else if (command.op === "eval") {
                try {
                    (0, eval)(command.code);
                } catch (error) {
                    console.error("domonic-libs command failed", error);
                }
            }
        });
    },

    // Reconcile the live DOM against freshly rendered markup in place. Blowing
    // away `document.body.innerHTML` on every event destroys the node the user
    // is interacting with -- a slider loses its drag mid-gesture, a text field
    // loses its caret. Morphing leaves untouched nodes (and their native state)
    // exactly where they are.
    applyHTML: function (markup) {
        var parsed = new DOMParser().parseFromString(
            "<body>" + markup + "</body>", "text/html"
        );

        // Hold onto the focused node (and its caret) so that if the morph
        // happens to blur it -- a field with no id/name can't be found again
        // by `restoreFocus` -- we can put focus straight back.
        var active = document.activeElement;
        var hadFocus = active && active !== document.body;
        var selStart = null;
        var selEnd = null;
        try {
            selStart = active.selectionStart;
            selEnd = active.selectionEnd;
        } catch (error) {
            // some input types throw on selectionStart access
        }

        this.morphChildren(document.body, parsed.body);

        if (
            hadFocus &&
            document.activeElement !== active &&
            document.contains(active) &&
            typeof active.focus === "function"
        ) {
            active.focus({ preventScroll: true });
            if (
                typeof selStart === "number" &&
                typeof active.setSelectionRange === "function"
            ) {
                try {
                    active.setSelectionRange(selStart, selEnd);
                } catch (error) {
                    // input types that don't support selection ranges
                }
            }
        }
    },

    morphChildren: function (fromParent, toParent) {
        var toNodes = toParent.childNodes;
        var i;

        for (i = 0; i < toNodes.length; i++) {
            var fromNode = fromParent.childNodes[i];

            if (!fromNode) {
                fromParent.appendChild(document.importNode(toNodes[i], true));
            } else {
                this.morphNode(fromNode, toNodes[i]);
            }
        }

        while (fromParent.childNodes.length > toNodes.length) {
            fromParent.removeChild(fromParent.lastChild);
        }
    },

    morphNode: function (fromNode, toNode) {
        var incompatible =
            fromNode.nodeType !== toNode.nodeType ||
            (fromNode.nodeType === 1 && fromNode.tagName !== toNode.tagName);

        if (incompatible) {
            fromNode.parentNode.replaceChild(
                document.importNode(toNode, true), fromNode
            );
            return;
        }

        if (fromNode.nodeType === 3 || fromNode.nodeType === 8) {
            if (fromNode.nodeValue !== toNode.nodeValue) {
                fromNode.nodeValue = toNode.nodeValue;
            }
            return;
        }

        if (fromNode.nodeType !== 1) {
            return;
        }

        this.morphAttributes(fromNode, toNode);
        this.morphChildren(fromNode, toNode);
    },

    morphAttributes: function (fromEl, toEl) {
        // Don't stomp the value / checked state of the control the user is
        // actively editing -- their live input wins until they move on.
        var focused = fromEl === document.activeElement;
        var live = { value: true, checked: true, selected: true };
        var i, attr;

        for (i = 0; i < toEl.attributes.length; i++) {
            attr = toEl.attributes[i];
            if (focused && live[attr.name]) {
                continue;
            }
            if (fromEl.getAttribute(attr.name) !== attr.value) {
                fromEl.setAttribute(attr.name, attr.value);
            }
        }

        for (i = fromEl.attributes.length - 1; i >= 0; i--) {
            attr = fromEl.attributes[i];
            if (focused && live[attr.name]) {
                continue;
            }
            if (!toEl.hasAttribute(attr.name)) {
                fromEl.removeAttribute(attr.name);
            }
        }

        if (focused) {
            return;
        }

        if (typeof fromEl.value === "string") {
            var next = toEl.getAttribute("value");
            if (next !== null && fromEl.value !== next) {
                fromEl.value = next;
            }
        }

        if (typeof fromEl.checked === "boolean") {
            fromEl.checked = toEl.hasAttribute("checked");
        }
    },

    eventPayload: function (event) {
        var target = event.target || {};
        var currentTarget = event.currentTarget || target;
        var selectedOptions = target.selectedOptions
            ? Array.from(target.selectedOptions).map(function (option) {
                return {
                    label: option.label,
                    value: option.value,
                    selected: option.selected
                };
            })
            : [];
        var files = target.files
            ? Array.from(target.files).map(function (file) {
                return {
                    name: file.name,
                    size: file.size,
                    type: file.type,
                    lastModified: file.lastModified
                };
            })
            : [];
        var formData = {};
        var formElement = target.form || (
            String(target.tagName || "").toUpperCase() === "FORM" ? target : null
        );

        if (formElement) {
            Array.from(new FormData(formElement)).forEach(function (entry) {
                formData[entry[0]] = entry[1];
            });
        }

        return {
            type: event.type,
            timeStamp: event.timeStamp,
            bubbles: event.bubbles,
            cancelable: event.cancelable,
            composed: event.composed,
            detail: event.detail,
            target: {
                id: target.id || "",
                name: target.name || "",
                tagName: target.tagName || "",
                type: target.type || "",
                value: target.value,
                checked: target.checked,
                disabled: target.disabled,
                dataset: Object.assign({}, target.dataset || {}),
                selectedOptions: selectedOptions,
                files: files,
                formData: formData
            },
            currentTarget: {
                id: currentTarget.id || "",
                name: currentTarget.name || "",
                tagName: currentTarget.tagName || "",
                type: currentTarget.type || "",
                value: currentTarget.value,
                checked: currentTarget.checked,
                disabled: currentTarget.disabled,
                dataset: Object.assign({}, currentTarget.dataset || {})
            },
            value: target.value !== undefined ? target.value : currentTarget.value,
            checked: target.checked !== undefined ? target.checked : currentTarget.checked,
            key: event.key,
            code: event.code,
            repeat: event.repeat,
            altKey: event.altKey,
            ctrlKey: event.ctrlKey,
            metaKey: event.metaKey,
            shiftKey: event.shiftKey,
            button: event.button,
            buttons: event.buttons,
            clientX: event.clientX,
            clientY: event.clientY,
            pageX: event.pageX,
            pageY: event.pageY,
            screenX: event.screenX,
            screenY: event.screenY,
            offsetX: event.offsetX,
            offsetY: event.offsetY,
            movementX: event.movementX,
            movementY: event.movementY,
            pointerId: event.pointerId,
            pointerType: event.pointerType,
            pressure: event.pressure,
            deltaX: event.deltaX,
            deltaY: event.deltaY,
            deltaZ: event.deltaZ,
            deltaMode: event.deltaMode,
            inputType: event.inputType,
            data: event.data
        };
    },

    filesFromDataTransfer: function (dataTransfer) {
        if (!dataTransfer || !dataTransfer.files) {
            return [];
        }

        return Array.from(dataTransfer.files).map(function (file) {
            return {
                name: file.name,
                size: file.size,
                type: file.type,
                lastModified: file.lastModified,
                path: file.path || file.pywebviewFullPath || file.webkitRelativePath || ""
            };
        });
    },

    captureFocus: function () {
        var active = document.activeElement;

        if (!active || active === document.body) {
            return null;
        }

        return {
            id: active.id || "",
            name: active.name || "",
            tagName: active.tagName || "",
            type: active.type || "",
            selectionStart: active.selectionStart,
            selectionEnd: active.selectionEnd,
            scrollTop: active.scrollTop,
            scrollLeft: active.scrollLeft
        };
    },

    restoreFocus: function (state) {
        var selector;
        var element;

        if (!state) {
            return;
        }

        if (state.id) {
            selector = "#" + this.escapeSelector(state.id);
        } else if (state.name) {
            selector = '[name="' + this.escapeSelector(state.name) + '"]';
        }

        if (!selector) {
            return;
        }

        element = document.querySelector(selector);

        if (!element) {
            return;
        }

        if (document.activeElement === element) {
            // The morph kept this control alive, so its native caret / scroll
            // position are already correct -- re-applying the pre-event
            // selection here would fight the browser.
            return;
        }

        element.focus({ preventScroll: true });
        element.scrollTop = state.scrollTop || 0;
        element.scrollLeft = state.scrollLeft || 0;

        if (
            typeof state.selectionStart === "number" &&
            typeof element.setSelectionRange === "function"
        ) {
            element.setSelectionRange(state.selectionStart, state.selectionEnd);
        }
    },

    escapeSelector: function (value) {
        if (window.CSS && typeof window.CSS.escape === "function") {
            return window.CSS.escape(value);
        }

        return String(value).replace(/["\\\\]/g, "\\\\$&");
    },

    keepAwake: function () {
        // macOS App Nap + WKWebView throttle (and can suspend) JS timers and
        // the js_api bridge when the window is backgrounded, so events and
        // `app.every` timers silently stop round-tripping. A bare
        // requestAnimationFrame self-loop keeps the web-content process warm
        // enough that the bridge stays responsive. Desktop only -- browsers
        // never fire `pywebviewready`, and throttle hidden tabs regardless.
        if (this.awakeStarted) {
            return;
        }

        this.awakeStarted = true;

        var tick = function () {
            window.requestAnimationFrame(tick);
        };

        window.requestAnimationFrame(tick);
    }
};

window.addEventListener("pywebviewready", function () {
    window.__domonicUI.keepAwake();
});
"""
