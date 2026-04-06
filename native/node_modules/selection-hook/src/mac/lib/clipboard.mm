/**
 * Clipboard utility functions for text selection hook on macOS
 */

#import "clipboard.h"

/**
 * Reads text from clipboard
 * @param content [out] The string to store clipboard content
 * @return true if successful, false otherwise
 */
bool ReadClipboard(std::string &content)
{
    content.clear();

    @autoreleasepool
    {
        NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
        NSString *string = [pasteboard stringForType:NSPasteboardTypeString];

        if (string != nil)
        {
            content = std::string([string UTF8String]);
            return true;
        }

        return false;
    }
}

/**
 * Writes text to clipboard
 * @param content The string to write to clipboard
 * @return true if successful, false otherwise
 */
bool WriteClipboard(const std::string &content)
{
    if (content.empty())
        return false;

    @autoreleasepool
    {
        NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
        // have to clearContents first.
        [pasteboard clearContents];

        NSString *contentString = [NSString stringWithUTF8String:content.c_str()];
        BOOL success = [pasteboard setString:contentString forType:NSPasteboardTypeString];

        return success == YES;
    }
}

/**
 * Gets the current change count of clipboard
 * @return The change count of NSPasteboard
 *
 * Cost: ~2 us
 */
int64_t GetClipboardSequence()
{
    @autoreleasepool
    {
        NSPasteboard *pasteboard = [NSPasteboard generalPasteboard];
        return static_cast<int64_t>([pasteboard changeCount]);
    }
}