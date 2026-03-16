import { createRouter, createWebHistory } from 'vue-router';

import HomeView from '../views/HomeView.vue';
import DeviceView from '../views/DeviceView.vue';

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/device/:id', name: 'device', component: DeviceView, props: true },
  ],
});
