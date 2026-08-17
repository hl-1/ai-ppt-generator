package com.aippt.outline;

import java.io.Serializable;

public record OutlineSourceSection(String ref, String heading, int level, String text, String locator)
        implements Serializable {
}
