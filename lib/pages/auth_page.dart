import 'package:flutter/material.dart';
import 'package:identicare_mobile/services/auth_service.dart';
import 'package:provider/provider.dart';

class AuthPage extends StatefulWidget {
  const AuthPage({super.key});

  @override
  State<AuthPage> createState() => _AuthPageState();
}

class _AuthPageState extends State<AuthPage> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  bool _isLogin = true;
  bool _isLoading = false;

  void _submitAuthForm() async {
    if (!_formKey.currentState!.validate()) {
      return;
    }
    setState(() { _isLoading = true; });

    final authService = Provider.of<AuthService>(context, listen: false);
    String? error;

    if (_isLogin) {
      error = await authService.signIn(
        email: _emailController.text.trim(),
        password: _passwordController.text.trim(),
      );
    } else {
      error = await authService.signUp(
        email: _emailController.text.trim(),
        password: _passwordController.text.trim(),
      );
    }

    if (!mounted) return;
    setState(() { _isLoading = false; });

    if (error != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error), backgroundColor: Colors.redAccent),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(32.0),
          child: Form(
            key: _formKey,
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Icon(Icons.local_hospital_outlined, size: 80, color: Theme.of(context).colorScheme.primary),
                const SizedBox(height: 24),
                Text(
                  _isLogin ? 'Selamat Datang' : 'Buat Akun Baru',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 28, fontWeight: FontWeight.bold),
                ),
                const SizedBox(height: 8),
                Text(
                  _isLogin ? 'Login untuk melanjutkan' : 'Daftar untuk memulai perjalanan sehatmu',
                  textAlign: TextAlign.center,
                  style: TextStyle(fontSize: 16, color: Colors.grey.shade600),
                ),
                const SizedBox(height: 40),
                TextFormField(
                  controller: _emailController,
                  decoration: const InputDecoration(labelText: 'Email', prefixIcon: Icon(Icons.email_outlined)),
                  keyboardType: TextInputType.emailAddress,
                  validator: (value) => (value == null || !value.contains('@')) ? 'Masukkan email yang valid' : null,
                ),
                const SizedBox(height: 16),
                TextFormField(
                  controller: _passwordController,
                  decoration: const InputDecoration(labelText: 'Password', prefixIcon: Icon(Icons.lock_outline)),
                  obscureText: true,
                  validator: (value) => (value == null || value.length < 6) ? 'Password minimal 6 karakter' : null,
                ),
                const SizedBox(height: 32),
                _isLoading
                    ? const Center(child: CircularProgressIndicator())
                    : ElevatedButton(
                        onPressed: _submitAuthForm,
                        child: Text(_isLogin ? 'LOGIN' : 'REGISTER'),
                      ),
                const SizedBox(height: 16),
                TextButton(
                  onPressed: () {
                    if (_isLoading) return;
                    setState(() {
                      _isLogin = !_isLogin;
                    });
                  },
                  child: Text(_isLogin ? 'Belum punya akun? Register di sini' : 'Sudah punya akun? Login'),
                )
              ],
            ),
          ),
        ),
      ),
    );
  }
}
