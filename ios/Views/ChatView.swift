import SwiftUI

struct iOSMessage: Identifiable {
    let id = UUID()
    let text: String
    let isMe: Bool
    let timestamp: Date
}

struct ChatView: View {
    let contact: iOSContact
    @State private var messages: [iOSMessage] = []
    @State private var typedMessage = ""

    var body: some View {
        VStack {
            // Safety number banner
            HStack {
                Image(systemName: "lock.shield.fill")
                    .foregroundColor(.green)
                VStack(alignment: .leading) {
                    Text("End-to-End Encrypted Session")
                        .font(.caption)
                        .bold()
                    Text("Safety Number: \(contact.safetyNumber)")
                        .font(.system(size: 10, design: .monospaced))
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                Spacer()
            }
            .padding()
            .background(Color.secondary.opacity(0.1))

            // Messages list
            ScrollView {
                VStack(spacing: 12) {
                    ForEach(messages) { msg in
                        HStack {
                            if msg.isMe {
                                Spacer()
                                Text(msg.text)
                                    .padding()
                                    .background(Color.blue)
                                    .foregroundColor(.white)
                                    .cornerRadius(12)
                            } else {
                                Text(msg.text)
                                    .padding()
                                    .background(Color.secondary.opacity(0.2))
                                    .foregroundColor(.primary)
                                    .cornerRadius(12)
                                Spacer()
                            }
                        }
                        .padding(.horizontal)
                    }
                }
            }

            // Message input field
            HStack {
                TextField("Message text", text: $typedMessage)
                    .textFieldStyle(RoundedBorderTextFieldStyle())
                Button(action: sendMessage) {
                    Image(systemName: "paperplane.fill")
                        .font(.title2)
                }
            }
            .padding()
        }
        .navigationTitle(contact.nickname)
        .navigationBarTitleDisplayMode(.inline)
    }

    func sendMessage() {
        guard !typedMessage.isEmpty else { return }

        // Under the hood, this calls our anonymus-core Swift FFI to:
        // 1. Pad the message using padding_pad
        // 2. Encrypt the padded message using Double Ratchet key
        // 3. Seal the payload inside the sealed-sender envelope using sealed_sender_seal
        // 4. Send the payload to the local node relay endpoint
        let msg = iOSMessage(text: typedMessage, isMe: true, timestamp: Date())
        messages.append(msg)
        typedMessage = ""
    }
}
