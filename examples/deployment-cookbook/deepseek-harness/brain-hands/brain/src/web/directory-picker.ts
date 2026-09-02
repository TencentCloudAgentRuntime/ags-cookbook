import type { Context } from "@deepseek-ai/cordis";
import DirectoryPicker, {
  type DirectoryPickerNativeCapability,
} from "@deepseek-ai/dsh-host-directory-picker";

const unsupportedPicker: DirectoryPickerNativeCapability = {
  kind: "native",
  pick: async () => null,
};

/** Keeps the host API contract while Workspace creation is owned by the AGS flow. */
export default class AgsDirectoryPicker extends DirectoryPicker {
  public constructor(ctx: Context) {
    super(ctx);
  }

  public capability(): DirectoryPickerNativeCapability {
    return unsupportedPicker;
  }
}
