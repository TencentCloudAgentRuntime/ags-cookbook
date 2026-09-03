window.__ModuleLoader__.load({
  id: "@ags-cookbook/dsh-workspace-flow",
  factory: (require) => {
    const module = { exports: {} };
    const exports = module.exports;
    const React = require("react");
    const { Button, Modal } = require("@deepseek-ai/dsh-client-ui-primitives");

    const css = `
      .agsWorkspaceDialog.agsWorkspaceDialog { width: min(440px, calc(100vw - 32px)); padding: 0; }
      .agsWorkspaceBody { display: flex; flex-direction: column; gap: 18px; padding: 24px; }
      .agsWorkspaceTitle { margin: 0; color: var(--dsw-alias-label-primary); font-size: 18px; line-height: 26px; font-weight: 600; }
      .agsWorkspaceField { display: flex; flex-direction: column; gap: 8px; }
      .agsWorkspaceLabel { color: var(--dsw-alias-label-secondary); font-size: 13px; line-height: 20px; font-weight: 500; }
      .agsWorkspaceControl { box-sizing: border-box; width: 100%; height: 42px; border: 1px solid var(--dsw-alias-border-l2); border-radius: 10px; background: var(--dsw-alias-bg-layer-2); color: var(--dsw-alias-label-primary); padding: 0 12px; font: inherit; outline: none; }
      .agsWorkspaceControl:focus { border-color: var(--dsw-alias-button-info-fill); }
      .agsWorkspaceError { color: var(--dsw-alias-state-error-primary); font-size: 12px; line-height: 18px; }
      .agsWorkspaceActions { display: flex; justify-content: flex-end; gap: 8px; padding-top: 2px; }
    `;
    if (document.querySelector("style[data-plugin-css='ags-workspace-flow']") === null) {
      const style = document.createElement("style");
      style.dataset.pluginCss = "ags-workspace-flow";
      style.textContent = css;
      document.head.appendChild(style);
    }

    function failureMessage(error) {
      return error instanceof Error ? error.message : String(error);
    }

    function WorkspaceFlow(props) {
      const [name, setName] = React.useState("");
      const [oses, setOses] = React.useState([]);
      const [os, setOs] = React.useState("");
      const [loading, setLoading] = React.useState(false);
      const [submitting, setSubmitting] = React.useState(false);
      const [error, setError] = React.useState(null);

      React.useEffect(() => {
        if (!props.open) return;
        const controller = new AbortController();
        setName("");
        setOses([]);
        setOs("");
        setError(null);
        setLoading(true);
        fetch("/api/ags/workspace-options", { signal: controller.signal })
          .then(async (response) => {
            if (!response.ok) throw new Error("Could not load OS options");
            return response.json();
          })
          .then((body) => {
            const options = Array.isArray(body.oses) ? body.oses : [];
            setOses(options);
            setOs(options[0]?.id ?? "");
          })
          .catch((cause) => {
            if (!controller.signal.aborted) setError(failureMessage(cause));
          })
          .finally(() => {
            if (!controller.signal.aborted) setLoading(false);
          });
        return () => controller.abort();
      }, [props.open]);

      const busy = props.busy || loading || submitting;
      const submit = async () => {
        const title = name.trim();
        if (title === "") {
          setError("Enter a workspace name");
          return;
        }
        if (os === "") {
          setError("Select an OS");
          return;
        }
        setSubmitting(true);
        setError(null);
        try {
          const response = await fetch("/api/ags/workspaces", {
            method: "POST",
            headers: { "content-type": "application/json" },
            body: JSON.stringify({ name: title, os }),
          });
          const body = await response.json();
          if (!response.ok || typeof body.path !== "string") {
            throw new Error(typeof body.message === "string" ? body.message : "Could not create workspace");
          }
          props.onPicked(body.path);
        } catch (cause) {
          setError(failureMessage(cause));
        } finally {
          setSubmitting(false);
        }
      };

      return React.createElement(Modal, {
        open: props.open,
        onClose: () => { if (!busy) props.onCancel(); },
        title: "Add workspace",
        className: "agsWorkspaceDialog",
        headless: true,
      }, React.createElement("div", { className: "agsWorkspaceBody" },
        React.createElement("h2", { className: "agsWorkspaceTitle" }, "Add workspace"),
        React.createElement("label", { className: "agsWorkspaceField" },
          React.createElement("span", { className: "agsWorkspaceLabel" }, "Workspace name"),
          React.createElement("input", {
            className: "agsWorkspaceControl",
            value: name,
            disabled: busy,
            autoFocus: true,
            maxLength: 80,
            placeholder: "My workspace",
            onChange: (event) => setName(event.target.value),
            onKeyDown: (event) => {
              if (event.key === "Enter" && !busy) {
                event.preventDefault();
                void submit();
              }
            },
          }),
        ),
        React.createElement("label", { className: "agsWorkspaceField" },
          React.createElement("span", { className: "agsWorkspaceLabel" }, "OS"),
          React.createElement("select", {
            className: "agsWorkspaceControl",
            value: os,
            disabled: busy,
            onChange: (event) => setOs(event.target.value),
          }, oses.map((option) => React.createElement("option", {
            key: option.id,
            value: option.id,
          }, option.label))),
        ),
        error === null ? null : React.createElement("div", {
          className: "agsWorkspaceError",
          role: "alert",
        }, error),
        React.createElement("div", { className: "agsWorkspaceActions" },
          React.createElement(Button, {
            variant: "outline",
            disabled: busy,
            onClick: props.onCancel,
          }, "Cancel"),
          React.createElement(Button, {
            variant: "primary",
            disabled: busy || name.trim() === "" || os === "",
            onClick: () => { void submit(); },
          }, submitting ? "Creating…" : "Create"),
        ),
      ));
    }

    const inject = ["slots"];
    function apply(ctx) {
      ctx.slots.inject("conversation.hero.workspace.directoryFlow", () =>
        ctx.slots.inject("sidebar.workspaces.directoryFlow", function* () {
          yield ctx.slots.register({
            name: "conversation.hero.workspace.directoryFlow",
            priority: -1,
          }, WorkspaceFlow);
          yield ctx.slots.register({
            name: "sidebar.workspaces.directoryFlow",
            priority: -1,
          }, WorkspaceFlow);
        }));
    }

    exports.apply = apply;
    exports.inject = inject;
    return module.exports;
  },
});
