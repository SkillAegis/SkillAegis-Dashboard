<script setup>
import { ref } from 'vue'
import { faCircleNotch } from '@fortawesome/free-solid-svg-icons'
import { login } from '@/socket'
import { toast } from '@/utils'

const email = ref('')
const password = ref('')
const loginInProgress = ref(false)

async function handleSubmit() {
  loginInProgress.value = true
  const payload = { username: email.value, password: password.value }
  const result = await login(payload)
  if (!result.success) {
    toast({
      variant: result.success ? 'success' : 'danger',
      message: result.message,
      title: 'Login'
    })
  }
  loginInProgress.value = false
}

</script>

<template>
    <form @submit.prevent="handleSubmit" class="flex flex-col gap-4 text-slate-900">
        <div>
            <label for="email" class="block text-sm font-medium text-slate-700">Email</label>
            <input
            id="email"
            v-model="email"
            type="text"
            inputmode="email"
            autocomplete="email"
            required
            class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
        </div>

        <div>
            <label for="password" class="block text-sm font-medium text-slate-700">Password</label>
            <input
            id="password"
            v-model="password"
            type="password"
            required
            class="mt-1 w-full px-3 py-2 border border-slate-300 rounded-md shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
        </div>

        <button
            type="submit"
            class="btn btn-primary btn-lg w-full"
        >
            <FontAwesomeIcon :icon="faCircleNotch" v-show="loginInProgress" spin class="mr-1"></FontAwesomeIcon>
            <span>Sign In</span>
        </button>
    </form>
</template>