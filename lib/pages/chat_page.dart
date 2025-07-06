import 'package:flutter/material.dart';

class ChatPage extends StatefulWidget {
  final String doctorName;
  const ChatPage({super.key, required this.doctorName});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  final List<Map<String, String>> _messages = [
    {'sender': 'doctor', 'text': 'Selamat siang, ada yang bisa saya bantu?'},
  ];
  final _textController = TextEditingController();

  void _sendMessage() {
    if (_textController.text.isEmpty) return;
    setState(() {
      _messages.add({'sender': 'user', 'text': _textController.text});
      _textController.clear();
      // Simulasi balasan dokter
      Future.delayed(const Duration(seconds: 2), () {
        setState(() {
          _messages.add({'sender': 'doctor', 'text': 'Baik, saya mengerti. Bisa ceritakan lebih detail?'});
        });
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.doctorName),
        actions: [
          IconButton(onPressed: () {}, icon: const Icon(Icons.video_call_outlined)),
          IconButton(onPressed: () {}, icon: const Icon(Icons.call_outlined)),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final message = _messages[index];
                final isUser = message['sender'] == 'user';
                return _buildMessageBubble(isUser, message['text']!);
              },
            ),
          ),
          _buildMessageInput(),
        ],
      ),
    );
  }

  Widget _buildMessageBubble(bool isUser, String text) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: isUser ? Theme.of(context).colorScheme.primary : Colors.white,
          borderRadius: BorderRadius.only(
            topLeft: const Radius.circular(20),
            topRight: const Radius.circular(20),
            bottomLeft: isUser ? const Radius.circular(20) : Radius.zero,
            bottomRight: isUser ? Radius.zero : const Radius.circular(20),
          ),
          boxShadow: [
            BoxShadow(
              color: Colors.grey.withOpacity(0.1),
              blurRadius: 5,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Text(
          text,
          style: TextStyle(color: isUser ? Colors.white : Colors.black87),
        ),
      ),
    );
  }

  Widget _buildMessageInput() {
    return Container(
      padding: const EdgeInsets.all(8.0),
      decoration: BoxDecoration(
        color: Colors.white,
        boxShadow: [
          BoxShadow(
            color: Colors.grey.withOpacity(0.1),
            blurRadius: 10,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: SafeArea(
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _textController,
                decoration: const InputDecoration(
                  hintText: 'Ketik pesan...',
                  border: InputBorder.none,
                  filled: false,
                ),
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
            IconButton(
              icon: Icon(Icons.send, color: Theme.of(context).colorScheme.primary),
              onPressed: _sendMessage,
            ),
          ],
        ),
      ),
    );
  }
}
