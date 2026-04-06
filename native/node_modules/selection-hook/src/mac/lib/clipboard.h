/**
 * Clipboard utility functions for text selection hook on macOS
 */

#import <Cocoa/Cocoa.h>

#import <string>
/**
 * Reads text from clipboard
 * @param content [out] The string to store clipboard content
 * @return true if successful, false otherwise
 */
bool ReadClipboard(std::string &content);

/**
 * Writes text to clipboard
 * @param content The string to write to clipboard
 * @return true if successful, false otherwise
 */
bool WriteClipboard(const std::string &content);

/**
 * Gets the current change count of clipboard
 * @return The change count of NSPasteboard
 */
int64_t GetClipboardSequence();